from typing import Any, Dict, Optional

AUDIO_DOC_EXTS = (".mp3", ".wav", ".mp4", ".aac", ".ogg", ".oga", ".flac")

def pick_audio_from_message(msg: Dict[str, Any])-> Optional[Dict[str,Any]]:
    """
    Telegramのメッセージから最適な音声を抽出して返す。
    優先順: audio(mp3等) > document(音声拡張子/音声mime) > voice(ogg/opus) > video_note(丸動画)
    戻り値例: {"file_id": "...", "duration": 60, "source": "audio", "file_name": "x.mp3", "mime_type": "audio/mpeg"}
    """

    # 1:audio
    audio = msg.get("audio")
    if audio and audio.get("file_id"):
        return {
            "file_id": audio["file_id"],
            "duration": audio.get("duration"),
            "source":"audio",
            "file_name":audio.get('file_name'),
            'mime_type': audio.get("mime_type"),
        }
    
    # 2:documentファイルとして送られた音声
    doc = msg.get("document")
    if doc and doc.get("file_id"):
        fn = (doc.get("file_name") or "").lower()
        mt = (doc.get("mime_type") or "").lower()
        if fn.endswith(AUDIO_DOC_EXTS) or mt.startswith("audio/"):
            return {
                "file_id": doc["file_id"],
                "duration": None,
                "source": "document",
                "file_name": doc.get("file_name"),
                "mime_type": doc.get("mime_type"),
            }
    
    # 3:voiceメッセージの場合
    voice = msg.get("voice")
    if voice and voice.get("file_id"):
        return {
            "file_id": voice["file_id"],
            "duration": voice.get("duration"),
            "source": "voice",
            "file_name": None,
            "mime_type": "audio/ogg",
        }
    
    return None