import os , tempfile
from typing import List, Tuple
from pydub import AudioSegment

def split_wav_to_chunks(wav_path: str, chunk_ms: int = 30_000, overlap_ms: int = 1_500) -> List[Tuple[str, int, int]]:
    # wavをchunk_msごとに分割し、一時wavパスと開始/終了msを返す
    # オーバーラップを入れて切れ目の語欠落を防ぐ
    # 戻り：[(chunk_file_path, start_ms, end_ms)]
    audio = AudioSegment.from_wav(wav_path)
    chunks = []
    s =0
    n = len(audio)
    while s < n:
        e = min(s + chunk_ms, n)
        # オーバーラップ確保（次のchunkに1.5sかぶせる）
        segment = audio[s:e]
        td = tempfile.mkdtemp()
        out = os.path.join(td, f"chunk_{s}_{e}.wav")
        segment.export(out, format="wav")
        chunks.append((out, s, e))

        if e == n:
            break
        # 次は少し戻す
        s = e - overlap_ms
        if s < 0: s=0
    return chunks

def ms_to_ts(ms: int) -> str:
    s = ms // 1000
    return f"{s//60:02d}:{s%60:02d}"