from bardapi import Bard

bard = Bard(token='bQgxCfPTL1GwyoIr0s7tme5TDIaKrFwFVPY2pby6H6Sg1vnto5CbPmaau7Q06nFs6SI3fg.')
audio = bard.speech('what are planets?')
with open("speech.ogg", "wb") as f:
  f.write(bytes(audio['audio']))