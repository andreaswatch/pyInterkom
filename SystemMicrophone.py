import argparse
import asyncio
import json
import logging
import os
import platform
import ssl
import pyaudio
from threading import Thread, Event, Lock
import numpy as np
import av
import time
import signal
import sys
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRecorder, MediaBlackhole, MediaRelay 
from aiortc.rtcrtpsender import RTCRtpSender
from aiortc.mediastreams import MediaStreamTrack, AudioStreamTrack
import noisereduce as nr

'''A aiortc microphone implementation based on pyaudio'''
class SystemMicrophone(MediaStreamTrack):
    kind = "audio"
    
    '''audio = PyAudio instance'''
    def __init__(self, audio):
        super().__init__()
        self.audio        = audio

        self.INDEX        = 4
        device_info       = self.audio.get_device_info_by_index(self.INDEX)
        self.kind         = "audio"
        self.RATE         = int(device_info['defaultSampleRate']) #44100
        self.AUDIO_PTIME  = 0.020                                    # 20ms audio packetization
        self.SAMPLES      = int(self.AUDIO_PTIME * self.RATE)
        self.FORMAT       = pyaudio.paInt32
        self.CHANNELS     = int(device_info['maxInputChannels']) #2
        self.CHUNK        = int(self.RATE*self.AUDIO_PTIME)
        self.FORMATAF     = 's16'   #'s32'                           # s32_le
        self.LAYOUT       = 'stereo'
        self.sampleCount  = 0

        self.stream       = self.audio.open(format=self.FORMAT, 
                                            channels=self.CHANNELS,
                                            rate=self.RATE,
                                            input=True, 
                                            input_device_index=self.INDEX,
                                            frames_per_buffer=self.CHUNK)
        #thread
        self.micData          = None
        self.micDataLock      = Lock()
        self.newMicDataEvent  = Event()
        self.newMicDataEvent.clear()
        self.exit_event = Event()
        self.captureThread = Thread(target=self.capture)
        self.captureThread.start()
        

    def capture(self):
        while not self.exit_event.is_set():
            data  = np.fromstring(self.stream.read(self.CHUNK),dtype=np.int32)
            #data = nr.reduce_noise(y=data, sr=rate)
            
            with self.micDataLock:
                self.micData = data
                self.newMicDataEvent.set()
    
        
    async def recv(self):
        newMicData = None
            
        self.newMicDataEvent.wait()

        with self.micDataLock:
            data  = self.micData
            data  = (data/2).astype('int32')
            data  = np.array([(data>>16).astype('int16')])
            self.newMicDataEvent.clear()
        
        frame   = av.AudioFrame.from_ndarray(data, self.FORMATAF, layout=self.LAYOUT)
        frame.pts         = self.sampleCount
        frame.rate        = self.RATE
        self.sampleCount += frame.samples

        return frame

    def stop(self):
        self.exit_event.set()
        self.captureThread.join() 
