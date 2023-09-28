# noinspection PyShadowingNames
from contextlib import asynccontextmanager
from http import HTTPStatus
from importlib.metadata import files

import openai
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain.chains import ConversationalRetrievalChain
from langchain.chains.conversational_retrieval.base import BaseConversationalRetrievalChain
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import YoutubeAudioLoader, PyPDFLoader, Blob
from langchain.document_loaders.generic import GenericLoader
from langchain.document_loaders.parsers import OpenAIWhisperParser
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
from mysql.connector.types import RowType

from helper import *
from models.Message import Message, MessageResponse
from models.Response import Response
from models.User import UserSignup, UserLogin

load_dotenv()  # read local .env file
openai.api_key = os.getenv('OPENAI_API_KEY')
CHROMA_PERSIST_DIRECTORY = os.getenv('CHROMA_PERSIST_DIRECTORY', 'docs/chroma/')

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=150
)
qa: ConversationalRetrievalChain | None = None
vector_db: Chroma | None = None
db: PooledMySQLConnection | MySQLConnection | None = None


def load_qa(vector_db: Chroma) -> BaseConversationalRetrievalChain:
    retriever = vector_db.as_retriever(search_type='mmr', search_kwargs={'top_k': 5})
    return ConversationalRetrievalChain.from_llm(ChatOpenAI(temperature=0), retriever=retriever)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # On startup
    global qa, vector_db, db
    db = connect_to_database()
    vector_db = Chroma(persist_directory=CHROMA_PERSIST_DIRECTORY,
                       embedding_function=OpenAIEmbeddings())
    qa = load_qa(vector_db)

    yield  # When the app is running
    # On shutdown
    db.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.post('/')
def root(messages: list[Message]) -> MessageResponse:
    if not messages:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Messages are required',
        )

    chat_history = []
    for i in range(0, len(messages) - 1, 2):
        chat_history.append((messages[i].content, messages[i + 1].content))

    message = qa.run(question=messages[-1].content, chat_history=chat_history)
    messages.append(Message(role='assistant', content=message))
    return MessageResponse(messages=messages)


@app.post('/signup')
async def signup(user_signup: UserSignup) -> Response:
    mysql_query = 'SELECT * FROM users WHERE email = %s'
    with db.cursor() as cursor:
        cursor.execute(mysql_query, (user_signup.email,))
        result = cursor.fetchone()
        if result:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Email already exists',
            )

    hashed_password = get_hashed_password(user_signup.password)
    mysql_query = 'INSERT INTO users (name, email, password) VALUES (%s, %s, %s)'
    with db.cursor() as cursor:
        cursor.execute(mysql_query, (user_signup.name, user_signup.email, hashed_password))
        db.commit()

    return Response(message='Signup successful')


@app.post('/login')
async def login(user_login: UserLogin) -> Response:
    mysql_query = 'SELECT password FROM users WHERE email = %s'

    with db.cursor() as cursor:
        cursor.execute(mysql_query, (user_login.email,))
        result: RowType = cursor.fetchone()
        if not result:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail='Incorrect email',
            )

        password = bytes(result[0])

        if not is_correct_password(user_login.password, password):
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail='Incorrect password',
            )

    return Response(message='Login successful')


@app.post('/documents')
def upload_documents(files: list[UploadFile]) -> Response:
    docs = []
    for file in files:
        output_file = Path('docs/pdfs') / file.filename
        output_file.parent.mkdir(exist_ok=True, parents=True)
        output_file.write_bytes(file.file.read())
        docs.extend(PyPDFLoader(output_file.as_posix()).load())
        output_file.unlink()

    splits = text_splitter.split_documents(docs)
    vector_db.add_documents(splits)
    vector_db.persist()

    return Response(message=f'{len(files)} document(s) uploaded successfully')


@app.post('/images')
def upload_images(files: list[UploadFile]) -> Response:
    docs = []
    splits = []

    for file in files:
        parsed_text = extract_text_from_image(file.file, file.filename)
        docs.append(parsed_text)

    for doc in docs:
        splits.extend(text_splitter.split_text(doc))
    vector_db.add_texts(splits)
    vector_db.persist()

    return Response(message=f'{len(files)} images(s) uploaded successfully')


@app.post('/videos')
def upload_video(files: list[UploadFile]) -> Response:
    texts = []
    docs = []
    openai_whisper_parser = OpenAIWhisperParser()
    for file in files:
        output_file = Path('docs/videos') / file.filename
        output_file.parent.mkdir(exist_ok=True, parents=True)
        data = file.file.read()
        output_file.write_bytes(data)
        texts.extend(extract_text_from_video(output_file.as_posix()))

        audio_file = Path(extract_audio_from_video(output_file.as_posix()))

        blob = Blob.from_path(audio_file.as_posix())
        docs.extend(openai_whisper_parser.parse(blob))

        output_file.unlink()
        audio_file.unlink()

    split_texts = []
    for text in texts:
        split_texts.extend(text_splitter.split_text(text))
    split_docs = text_splitter.split_documents(docs)

    vector_db.add_documents(split_docs)
    vector_db.add_texts(split_texts)
    vector_db.persist()

    return Response(message=f'{len(files)} video(s) uploaded successfully')


@app.post('/youtube')
def load_youtube_transcript(url: str) -> Response:
    youtube_audio_save_dir = Path('docs/youtube')
    youtube_audio_save_dir.mkdir(exist_ok=True, parents=True)

    loader = GenericLoader(
        YoutubeAudioLoader([url], youtube_audio_save_dir.as_posix()),
        OpenAIWhisperParser()
    )
    docs = loader.load()
    text_splitter.split_documents(docs)
    vector_db.add_documents(docs)
    vector_db.persist()

    return Response(message=f'{url} uploaded successfully')


if __name__ == '__main__':
    uvicorn.run(app, host='localhost', port=8000)
