var pc = null;

function negotiate() {
    pc.addTransceiver('video', {direction: 'recvonly'}); //what about sendrecv?
    pc.addTransceiver('audio', {direction: 'sendrecv'}); //what about sendrecv?
    return pc.createOffer().then(function(offer) {
        return pc.setLocalDescription(offer);
    }).then(function() {
        // wait for ICE gathering to complete
        return new Promise(function(resolve) {
            if (pc.iceGatheringState === 'complete') {
                resolve();
            } else {
                function checkState() {
                    if (pc.iceGatheringState === 'complete') {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                }
                pc.addEventListener('icegatheringstatechange', checkState);
            }
        });
    }).then(function() {
        var offer = pc.localDescription;
        return fetch('/offer', {
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type,
            }),
            headers: {
                'Content-Type': 'application/json'
            },
            method: 'POST'
        });
    }).then(function(response) {
        return response.json();
    }).then(function(answer) {
        return pc.setRemoteDescription(answer);
    }).catch(function(e) {
        alert(e);
    });
}
function start() {
    var config = {
        sdpSemantics: 'unified-plan'
    };

    if (document.getElementById('use-stun').checked) {
        config.iceServers = [{urls: ['stun:stun.l.google.com:19302']}];
    }

    pc = new RTCPeerConnection(config);

    // connect audio / video
    pc.addEventListener('track', function(evt) {
        if (evt.track.kind == 'video') {
            document.getElementById('video').srcObject = evt.streams[0];
        } else {
            document.getElementById('audio').srcObject = evt.streams[0];
        }
    });

    document.getElementById('start').style.display = 'none';

    // get access to the microphone and start negotiation
    navigator.mediaDevices.getUserMedia({audio: true}).then(function(stream) {
        stream.getTracks().forEach(function(track) {
            pc.addTrack(track, stream);
        });
        negotiate();
    });

    document.getElementById('stop').style.display = 'inline-block';
}


function stop() {
    document.getElementById('stop').style.display = 'none';
    document.getElementById('start').style.display = 'initial';


    // close peer connection
    setTimeout(function() {
        pc.close();
    }, 500);
}