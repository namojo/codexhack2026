#!/usr/bin/env python3
"""Reproducible synthetic noisy call and DSP comparison; never a real 119 call."""
import argparse, json, subprocess, tempfile, wave
from pathlib import Path
import numpy as np
TEXT = '여기는 가상동 한빛복합센터 지하 이층 주차장이에요. 기둥 씨 공 칠 근처에 여자 세 명이 있어요. 할머니와 여자아이, 저예요. 비상등만 켜져 있고 물이 계속 들어와요. 계단으로 나갈 수 없어요.'

def save(path, samples, rate):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((np.clip(samples,-.98,.98)*32767).astype('<i2').tobytes())

def generate(out):
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='synthetic-parking-voice-') as tmp:
        aiff=Path(tmp)/'voice.aiff'; wav=Path(tmp)/'voice.wav'
        subprocess.run(['say','-v','Yuna','-r','155','-o',str(aiff),TEXT],check=True)
        subprocess.run(['afconvert','-f','WAVE','-d','LEI16','-c','1',str(aiff),str(wav)],check=True)
        with wave.open(str(wav)) as w:
            rate=w.getframerate(); clean=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768
    if len(clean) < rate*3: raise RuntimeError("TTS produced no usable speech; run with macOS speech service access")
    clean=np.pad(clean,(rate,int(rate*.6))); rng=np.random.default_rng(1192026)
    t=np.arange(len(clean))/rate
    rain=rng.normal(0,1,len(clean)); rumble=np.convolve(rain,np.ones(150)/150,mode='same')
    noise=.022*rain+.14*rumble+.024*np.sin(2*np.pi*95*t)+.008*np.sin(2*np.pi*180*t)
    noisy=clean+noise
    noisy*=.92/max(1.,np.max(np.abs(noisy)))
    # Estimate noise from first 0.7 s of the noisy input only, then spectral attenuation.
    size=1024; hop=256; window=np.hanning(size); padded=np.pad(noisy,(size,size))
    frames=np.lib.stride_tricks.sliding_window_view(padded,size)[::hop].copy()
    spectrum=np.fft.rfft(frames*window,axis=1)
    profile=np.mean(np.abs(spectrum[:max(1,int(.7*rate/hop))]),axis=0)
    magnitude=np.abs(spectrum); gain=np.maximum(.16,1.-1.25*profile[None,:]/(magnitude+1e-8))
    freq=np.fft.rfftfreq(size,1/rate); gain[:,freq<180]*=.12; gain[:,freq>6500]*=.2
    reconstructed=np.fft.irfft(spectrum*gain,axis=1)*window
    enhanced=np.zeros(len(padded)); weight=np.zeros(len(padded))
    for k,frame in enumerate(reconstructed):
        start=k*hop; enhanced[start:start+size]+=frame; weight[start:start+size]+=window**2
    enhanced=(enhanced/np.maximum(weight,1e-8))[size:size+len(noisy)]
    save(out/'parking-call-noisy.wav',noisy,rate); save(out/'parking-call-enhanced.wav',enhanced,rate)
    return {'synthetic':True,'transcript_source':'TTS script, not ASR','transcript':TEXT,'seconds':round(len(noisy)/rate,2),'sample_rate':rate,'noise_seed':1192026,'processing':'noise-only prefix estimate + STFT spectral attenuation and frequency filtering, applied to noisy input; not speaker separation','peak_noisy':float(np.max(np.abs(noisy))),'peak_enhanced':float(np.max(np.abs(enhanced)))}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('data/media'));a=p.parse_args()
    print(json.dumps(generate(a.output),ensure_ascii=False,indent=2))
