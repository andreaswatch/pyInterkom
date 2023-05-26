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

ROOT = os.path.dirname(__file__)
def printAudioDevices():
    p = pyaudio.PyAudio()

    # Get the total number of audio devices
    device_count = p.get_device_count()

    # Iterate over the devices and print their names and indices
    for i in range(device_count):
        device_info = p.get_device_info_by_index(i)
        print(f"Device {i}: {device_info['name']}")
        print(f"   maxInputChannels:  {device_info['maxInputChannels']}")
        print(f"   maxOutputChannels:  {device_info['maxOutputChannels']}")
        print(f"   defaultSampleRate: {device_info['defaultSampleRate']}")
printAudioDevices()

class SystemMic(MediaStreamTrack):
    kind = "audio"
    
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
        self.captureThread.join() #was:
        #self.captureThread.kill()

class AudioPlayerTrack():
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


def force_codec(pc, sender, forced_codec):
    kind = forced_codec.split("/")[0]
    codecs = RTCRtpSender.getCapabilities(kind).codecs
    transceiver = next(t for t in pc.getTransceivers() if t.sender == sender)
    transceiver.setCodecPreferences(
        [codec for codec in codecs if codec.mimeType == forced_codec]
    )


async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)



async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


mic = None


def stop_script(signal, frame):
    global mic
    mic.stop()
    sys.exit(0)


async def offer(request):
    global mic
    params = await request.json()
    print(" ------- Offer -------")
    print("offer sdp: " + str(params["sdp"]))
    print("offer type: " + str(params["type"]))    
    print(" ------- /Offer -------")

    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)
       

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    audio = pyaudio.PyAudio()

    mic = SystemMic(audio)
    mic_sender = pc.addTrack(mic)
    if args.audio_codec:
        force_codec(pc, mic_sender, args.audio_codec)
    elif args.play_without_decoding:
        raise Exception("You must specify the audio codec using --audio-codec")    

    #receiver = BrowserAudioReceiver(audio)
    #pc.addTrack(receiver)

    speaker = AudioPlayerTrack(audio)

    @pc.on("track")
    async def on_track(track):
        if track.kind == "audio":
            await speaker.play(track)
            print("end")
                    
            @track.on("ended")
            async def on_ended():
                stop_script(None, None) #stops the mic
        else:
            print("got a track of kind: " + str(track.kind))

    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


pcs = set()


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC webcam demo")
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument("--play-from", help="Read the media from a file and sent it."),
    parser.add_argument(
        "--play-without-decoding",
        help=(
            "Read the media without decoding it (experimental). "
            "For now it only works with an MPEGTS container with only H.264 video."
        ),
        action="store_true",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--verbose", "-v", action="count")
    parser.add_argument(
        "--audio-codec", help="Force a specific audio codec (e.g. audio/opus)"
    )
    parser.add_argument(
        "--video-codec", help="Force a specific video codec (e.g. video/H264)"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logging.basicConfig(level=logging.ERROR)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_post("/offer", offer)
    web.run_app(app, host=args.host, port=args.port, ssl_context=ssl_context)