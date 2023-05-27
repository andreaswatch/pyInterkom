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
from SystemMicrophone import SystemMicrophone
from SystemSpeaker import SystemSpeaker

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

    mic = SystemMicrophone(audio)
    mic_sender = pc.addTrack(mic)
    if args.audio_codec:
        force_codec(pc, mic_sender, args.audio_codec)
    elif args.play_without_decoding:
        raise Exception("You must specify the audio codec using --audio-codec")    

    speaker = SystemSpeaker(audio)

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