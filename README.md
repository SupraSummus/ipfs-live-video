Trial to do webcam streaming over IPFS.

Try it
------

Run `server.py` and collect chunk hashes. This needs `ffmpeg` to be available and local IPFS daemon.

    python server.py > chunks

Serve chunk hashes using websocket. `websocketd` is a great tool for that.

    websocketd --port=9000 tail -f chunks

After you have a server set up open published version of `client.html` (hash available in `publshed_version`). Pass websocket address in hash part of URL.

TODOs
-----

 * add audio/video synchronization
 * allow parameters for server
 * add timeout (max lag time) for client
 * maybe some other video format and codecs (mp4?)
 * server should take video in stdin
 * pin new and unpin old chunks
