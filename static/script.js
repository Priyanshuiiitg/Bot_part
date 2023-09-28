document.addEventListener("DOMContentLoaded", function () {
    const chatLog = document.getElementById("chat-log");
    const userInput = document.getElementById("user-input");
    const sendButton = document.getElementById("send-button");
//    const audioImages=document.querySelectorAll(".audio-image")

//    audioImages.forEach(function (audioImage) {
//     audioImage.addEventListener('click', function () {
//       // Get the audio source URL from the data-audio-src attribute
//       var audioSrc = audioImage.getAttribute('data-audio-src');
      
//       // Create a new audio element
//       var audio = new Audio(audioSrc);
      
//       // Play the audio
//       audio.play();
//     });
//   });
    function appendUserMessage(message) {
        const userMessage = document.createElement("div");
        userMessage.className = "user-message";
        userMessage.textContent = message;
        chatLog.appendChild(userMessage);

        // $(document).ready(function(){
        //     console.log("Ready to play....")
        //     var audio = "../speech.mp3";
        //     $('#audio-player').html("<audio controls><source src='" + audio + "' type='audio/mp3'></audio>");
        // });
        
    }

    function appendBotMessage(message) {
        const botMessage = document.createElement("div");
        botMessage.className = "bot-message";
        botMessage.textContent = message;
        chatLog.appendChild(botMessage);
    }

    sendButton.addEventListener("click", function () {
        const userMessage = userInput.value.trim();
        if (userMessage !== "") {
            appendUserMessage(userMessage);
            userInput.value = "";

            // Send user message to the server
            fetch("/ask", {
                method: "POST",
                body: new URLSearchParams({ user_input: userMessage }),
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            })
            .then(response => response.json())
            .then(data => {
                const botResponse = data.bot_response;
                appendBotMessage(botResponse);
            })
            .catch(error => console.error(error));
        }
    });

    const imageInput = document.getElementById('image-input');
    const statusDiv = document.getElementById('status');
    const uploadImage = document.getElementById('upload-image');

    uploadImage.addEventListener('click', () => {
        imageInput.click(); // Trigger file input when the image is clicked
    });

    imageInput.addEventListener('change', async () => {
      
        const formData = new FormData();
        formData.append('image', imageInput.files[0]);
appendBotMessage("Image uploaded successfully!!")
        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                const data = await response.json();
                appendBotMessage(data.message);
                // statusDiv.innerHTML = `<p>${data.message}</p>`;
            } else {
                statusDiv.innerHTML = '<p>File upload failed.</p>';
            }
        } catch (error) {
            statusDiv.innerHTML = `<p>Error: ${error.message}</p>`;
        }
    });

    // Focus on the input field when the page loads
    userInput.focus();
});
