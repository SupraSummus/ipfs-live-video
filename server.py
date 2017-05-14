import subprocess
from tempfile import TemporaryDirectory
import os
import requests
import time
import sys


class VideoServer:

    def __init__(self):
        self.encoder_process = None
        self.tmp_dir = None

        self.streams = {
            'video': {
                'input': ['-f', 'v4l2', '-i', '/dev/video0', '-r', '30'],
                'codec': ['-c:v', 'libvpx',
                    '-g', '30',
                    '-threads', '8',
                    '-deadline', 'realtime',
                ],
                'mime_codec': 'video/webm; codecs="vp8"',
            },
            'audio': {
                'input': ['-f', 'alsa', '-i', 'default'],
                'codec': ['-c:a', 'libvorbis',
                    #'-b:a', '128k',
                    #'-ar', '44100',
                ],
                'mime_codec': 'video/webm; codecs="vorbis"',
            },
        }
        self.check_interval = 0.5

    def process_header(self, stream, header_file_name):
        raise NotImplementedError()

    def process_chunk(self, stream, chunk_file_name):
        raise NotImplementedError()

    def start_encoder(self):
        cmd = ['ffmpeg']
        mapping = {}
        i = 0
        for name, stream in self.streams.items():
            cmd.extend(stream['input'])
            mapping[name] = i
            i += 1
        for name, stream in self.streams.items():
            cmd.extend(['-map', '{}:0'.format(mapping[name])])
            cmd.extend(stream['codec'])
            cmd.extend([
                '-f', 'webm_chunk',
                '-header', os.path.join(self.tmp_dir, 'header_{}'.format(name)),
                os.path.join(self.tmp_dir, 'chunk_{}_%d'.format(name)),
            ])
        return subprocess.Popen(cmd)

    def run(self):
        with TemporaryDirectory() as tmp_dir:
            self.tmp_dir = tmp_dir
            self.encoder_process = self.start_encoder()

            while True:

                for f in os.listdir(self.tmp_dir):
                    abs_f = os.path.join(self.tmp_dir, f)
                    parts = f.split('_')
                    {
                        'header': self.process_header,
                        'chunk': self.process_chunk,
                    }[parts[0]](parts[1], abs_f)
                    os.remove(abs_f)

                time.sleep(self.check_interval)

            self.encoder_process.wait()


class IPFSVideoServer(VideoServer):

    def __init__(self, *args, **kwargs):
        self.add_url = 'http://localhost:5001/api/v0/add'
        self.add_link_url = 'http://localhost:5001/api/v0/object/patch/add-link'

        self.header_hashes = {}
        self.stream_hashes = {}
        self.last_chunk_hash = None

        super().__init__(*args, **kwargs)

    def ipfs_add(self, buff, links={}, pin=False):
        r = requests.post(
            self.add_url,
            files={'data': ('data', buff, 'application/octet-stream')},
            params={'pin': pin}
        )
        r.raise_for_status()
        hash = r.json()['Hash']
        for name, target in links.items():
            hash = self.add_link(name, target, hash)
        return hash

    def ipfs_add_file(self, filename, *args, **kwargs):
        with open(filename, 'rb') as f:
            return self.ipfs_add(f, *args, **kwargs)

    def ipfs_wrap(self, hash, *args, **kwargs):
        return self.ipfs_add(hash.encode('UTF-8'), {'target': hash}, *args, **kwargs)

    def add_link(self, name, target, hash):
        r = requests.post(
            self.add_link_url,
            params=[
                ('arg', hash),
                ('arg', name),
                ('arg', target),
            ]
        )
        r.raise_for_status()
        return r.json()['Hash']

    def process_header(self, stream, header_file):
        self.header_hashes[stream] = self.ipfs_add_file(header_file)
        self.stream_hashes[stream] = self.ipfs_wrap(self.ipfs_add(self.header_hashes[stream].encode('UTF-8'), {
            'header': self.header_hashes[stream],
            'mime_codec': self.ipfs_add(self.streams[stream]['mime_codec']),
        }))

    def process_chunk(self, stream, chunk_file):
        if stream not in self.stream_hashes:
            print('ignoring chunk from stream {} beacuse of missing header'.format(stream), file=sys.stderr)
        links = {
            'stream': self.stream_hashes[stream],
        }
        self.last_chunk_hash = self.ipfs_add_file(chunk_file, links)
        sys.stdout.write('{}\n'.format(self.last_chunk_hash))
        sys.stdout.flush()


if __name__ == '__main__':
    IPFSVideoServer().run()
