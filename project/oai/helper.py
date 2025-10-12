# def transcribe(file_path: str) -> tuple[str,float]:
#     with open(file_path, 'rb') as f:
#         tr = oai.audio.transcriptions.create(
#             model='gpt-4o-transcribe',
#             file=f,
#         )
#         text = getattr(tr, 'text', None) or getattr(tr, 'text', '')
#         return text, 0.9