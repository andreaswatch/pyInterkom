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

'''A aiortc speaker implementation based on pyaudio'''
class SystemSpeaker():
    kind = "audio"

    def __init__(self, audio):
        super().__init__()
        self.track = None
        self.audio = pyaudio.PyAudio()
        self.INDEX        = 0
        device_info       = self.audio.get_device_info_by_index(self.INDEX)
        print(device_info['name'])
        self.kind         = "audio"
        self.RATE         = int(device_info['defaultSampleRate']) #44100
        self.AUDIO_PTIME  = 0.020                                    # 20ms audio packetization
        self.SAMPLES      = int(self.AUDIO_PTIME * self.RATE)
        self.FORMAT       = pyaudio.paInt32
        self.CHANNELS     = int(device_info['maxOutputChannels']) #2
        self.CHUNK        = int(self.RATE*self.AUDIO_PTIME)
        self.FORMATAF     = 's32_le'   #'s32'                           # s32_le
        self.LAYOUT       = 'stereo'
        self.sampleCount  = 0

        self.stream       = self.audio.open(format=self.FORMAT, 
                                            channels=self.CHANNELS,
                                            rate=self.RATE,
                                            output=True, 
                                            input_device_index=self.INDEX,
                                            frames_per_buffer=self.CHUNK)

    async def play(self, track):
        try:
            while True:
                frame = await track.recv()
                if frame:
                    data = frame.to_ndarray()
                    data = data.astype('int32') << 16
                    self.stream.write(data.tobytes())
        except Exception as e:
            print(f"Error while receiving frames: {e}")

    def stop(self):
        try:
            self.stream.stop_stream()
        except:
            pass
        try:
            self.stream.close()
        except:
            pass
        try:
            self.audio.terminate()
        except:
            pass
