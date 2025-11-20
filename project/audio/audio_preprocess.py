import os, tempfile
import numpy as np
import soundfile as sf
from pydub import AudioSegment
import webrtcvad
import noisereduce as nr
from scipy.signal import butter, sosfiltfilt,iirpeak
from typing import Optional


def _to_wav16k_mono(src_path:str) -> str:
    audio = AudioSegment.from_file(src_path)
    audio = audio.set_frame_rate(16000).set_channels(1)
    td = tempfile.mkdtemp()
    out = os.path.join(td, "stage0_16kl_mono_wav")
    audio.export(out, format="wav")
    return out

def _read_wav(path: str) -> tuple[np.ndarray, int]:
    # dtype は、その配列のデータ型。float32 / float64値は範囲がだいたい -1.0 ～ +1.0 に正規化されている
    y, sr = sf.read(path, dtype="float32")
    if y.ndim >1:
        y = np.mean(y, axis=1)
    return y, sr

def _write_wav(path:str, y: np.ndarray, sr:int):
    y = np.clip(y, -1.0, 1.0).astype(np.float32)
    sf.write(path, y, sr, subtype="PCM_16")

def _butter_sos_band(lc: Optional[float], hc: Optional[float], sr:int, order:int=4):
     # lc/hc: cutoff Hz（None は通過）
     if lc and hc :
         return butter(order, [lc/(sr/2), hc/(sr/2)], btype="bandpass", output="sos")
     if lc:
         return butter(order, lc/(sr/2), btype='highpass', output="sos")
     if hc:
         return butter(order, hc/(sr/2), btype='lowpass', output="sos")
     return None

def _eq_peaking(y: np.ndarray, sr:int, f0:float, q:float=1.0, gain_db: float=3.0) -> np.ndarray:
    w0 = f0 / (sr/2)
    b,a = iirpeak(w0, q)
    y_f = sosfiltfilt(_ba_to_sos(b, a), y)
    gain = 10 ** (gain_db / 20.0)
    return y + (y_f - y) * (gain -1.0)

def _ba_to_sos(b,a):
    # biquad化の簡易ラッパ（scipyのsosfiltfilt用
    from scipy.signal import tf2sos
    return tf2sos(b,a)

def _normalize_peak(y: np.ndarray, peak_db: float=-1.0) -> np.ndarray:
    # 目標ピーク dBFS に合わせる（簡易）
    peak = np.max(np.abs(y)) + 1e-9
    target = 10 ** (peak_db / 20.0)
    return y * (target / peak)

def _vad_trim(y: np.ndarray, sr: int, aggressiveness: int = 2) -> np.ndarray:
    """
    webrtcvad: 16-bit PCM で 10/20/30ms フレーム必要 → ここでは 20ms
    無音区間を大きく削って STTの混乱を減らす
    """
    vad = webrtcvad.Vad(aggressiveness)
    frame_ms = 20
    frame_len = int(sr * frame_ms / 1000)
    # 端数切り落とし
    n = len(y) - (len(y) % frame_len)
    y = y[:n]
    # float32 -> int16
    pcm16 = (y *32767).astype(np.int16).tobytes()

    voiced = []
    for i in range(0, len(pcm16), frame_len *2):
        chunk = pcm16[i:i + frame_len *2]
        if len(chunk) < frame_len * 2:
            break
        ok = vad.is_speech(chunk, sample_rate=sr)
        voiced.append(ok)
    
    # すべて無音判定ならそのまま
    if not any(voiced):
        return y
    
    # 連結
    frames = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) /32767.0
    frames = frames.reshape(-1, frame_len)
    keep = [frames[i] for i, ok in enumerate(voiced) if ok]
    y_new = np.concatenate(keep) if keep else y
    return y_new

def _rms(x:np.ndarray)-> float:
    return float(np.sqrt(np.mean(np.square(x) + 1e-12)))

def _agc_and_compress(y: np.ndarray, target_rms_db: float =-20.0,
                      threshhold_db: float = -18.0, ratio:float = 3.0) -> np.ndarray:
    # 1: RMSをtarget_rms_dbに合わせてゲイン調整（AGC）
    # 2: しきい値以上をratioで圧縮（軽めのコンプ）
    # AGC
    cur = _rms(y)
    target = 10 ** (target_rms_db / 20.0)
    if cur > 0:
        y = y * (target/cur)
    
    thr = 10 ** (threshhold_db / 20.0)
    sign = np.sign(y)
    mag = np.abs(y)
    over = mag > thr
    mag[over] = thr + (mag[over] - thr) / ratio
    y = sign * mag
    return y

def preprocess_for_stt(src_path: str, vad_aggr: int =2) -> str:
    # 1 16kHz mono変換
    # 2 ノイズ低減(最初の0.5秒を参照、ダメなら全体で軽め)
    # 3 HPF/LPF (-70Hzカット/ - 7kHzカット)で轟音・超高域を抑制
    # 4 フォルトマン帯を穏やかにEQ(-700Hz, -1500Hzを +2-3db)
    # 5 ピーク正規化(-1dBFS)
    # 6 VADで無音・雑音区間を削除

    # 0 to 16k mono wav
    stage0 = _to_wav16k_mono(src_path)
    y, sr = _read_wav(stage0)


    # 1 Noise reduction
    ref_samples = min(int(sr * 0.5), len(y))
    try:
        if ref_samples > sr // 10:
            y = nr.reduce_noise(y=y, sr=sr, prop_decrease=0.6, stationary=True)
        else:
            y = nr.reduce_noise(y=y, sr=sr, prop_decrease=0.6, stationary=True)
    except Exception:
        pass

    # 2 Band Limiting: 70Hz HPF / 7kHz LPF
    sos = _butter_sos_band(70.0, 7000.0, sr, order=4)
    if sos is not None:
        y = sosfiltfilt(sos,y)
    
    # Vowel-freidnly EQ: gentle peaks near -700Hz and -1500
    try:
        y = _eq_peaking(y, sr, f0=700.0, q=1.2, gain_db=2.5)
        y = _eq_peaking(y, sr, f0=1500.0, q=1.2, gain_db=2.0)
    except Exception:
        pass

    # 4 Peak normalise
    y = _normalize_peak(y, peak_db=-1.0)

    y = _agc_and_compress(y, target_rms_db= -20.0, threshhold_db=10.0, ratio=3.0)

    # 5 VAD-based trimming
    try:
        y = _vad_trim(y, sr, aggressiveness=vad_aggr)
    except Exception:
        pass
    
    # 6 出力
    td = tempfile.mkdtemp()
    out = os.path.join(td, "preprocessed_16k_mono.wav")
    _write_wav(out, y, sr)
    return out