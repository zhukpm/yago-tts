import re
import subprocess
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import requests


class FFmpeg(object):
    def __init__(self, ffmpeg_cli='ffmpeg'):
        self.ffmpeg_cli = ffmpeg_cli

    def convert_to_mp3(self, file_path):
        if file_path.suffix[1:] != 'mp3':
            mp3_path = file_path.parent.joinpath(file_path.stem + ".mp3")
            subprocess.run(
                [self.ffmpeg_cli, "-y", "-i",
                 f'{file_path.absolute()}', f'{mp3_path.absolute()}'
                 ]
            )
            return mp3_path
        return file_path

    def concatenate_files(self, paths, target_path):
        esc_paths = [f'{path_.absolute()}' for path_ in paths]
        subprocess.run(
            [self.ffmpeg_cli, "-y", "-i",
             f"concat:{'|'.join(esc_paths)}", "-c", "copy",
             f'{target_path.absolute()}'
             ]
        )


class TTSProvider(ABC):
    def __init__(self, ffmpeg=FFmpeg()):
        self.ffmpeg = ffmpeg
        self.patterns_dict = {}

    def synthesize(self, file_name):
        """
        :param file_name: text file to synthesize
        :return: Path to the resulting .mp3 file
        """
        file_path = Path(file_name)
        text_chunks = self.build_text_chunks(file_path)

        parts_dir = file_path.parent.joinpath('tts-synth-parts')
        if not parts_dir.is_dir():
            parts_dir.mkdir()

        chunk_paths = []
        for ind, text_chunk in enumerate(text_chunks):
            chunk_paths.append(self.synthesize_chunk(text_chunk, parts_dir, f"{file_path.stem}{ind}"))

        target_path = file_path.parent.joinpath(
            file_path.stem + '_' + datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + chunk_paths[0].suffix)
        self.ffmpeg.concatenate_files(chunk_paths, target_path)

        return self.ffmpeg.convert_to_mp3(target_path)

    @abstractmethod
    def synthesize_chunk(self, text_chunk, chunk_folder, chunk_file_stem):
        return None

    def preprocess_line(self, text_line):
        patterns = {re.compile(k): v for k, v in self.patterns_dict.items()}
        for pat, repl in patterns.items():
            text_line = pat.sub(repl, text_line)
        return text_line

    def build_text_chunks(self, file_path):
        chunks, chunk_limit = [""], 4990  # Text length limit is 5000 at google & yandex
        current, current_length = 0, 0
        with file_path.open('rt', encoding='utf-8') as fh:
            for line in fh:
                line = self.preprocess_line(line)
                if current_length + len(line) > chunk_limit:
                    if len(line) > chunk_limit:
                        # Line itself is too long
                        chunks.append("")
                        current += 1
                        current_length = 0

                        index = 0
                        while index < len(line):
                            for char_ in r'.;:, ':
                                char_index = line[index:index + chunk_limit].rfind(char_)
                                if char_index > 0:
                                    break
                            if char_index < 0:
                                char_index = chunk_limit - 1
                            if current_length + char_index > chunk_limit:
                                chunks.append("")
                                current += 1
                                current_length = 0
                            chunks[current] += line[index:index + char_index + 1]
                            current_length += char_index + 1
                            index += char_index + 1
                    else:
                        chunks.append(line)
                        current += 1
                        current_length = len(line)
                else:
                    chunks[current] += line
                    current_length += len(line)
        return chunks


class YandexTTS(TTSProvider):

    def __init__(self, folder_id, iam_token, ffmpeg=FFmpeg(), **kwargs):
        """
        Uses Yandex Text-to-speech API. See https://cloud.yandex.ru/docs/speechkit/tts/
        :param folder_id: Folder ID to use
        :param iam_token: IAM Token to use
        :param ffmpeg: ffmpeg tool to perform operations
        :param kwargs: HTTP-request parameters (see https://cloud.yandex.ru/docs/speechkit/tts/request)
        """
        super().__init__(ffmpeg)

        self.tts_args = kwargs
        self.tts_args.setdefault('lang', 'ru-RU')
        self.tts_args.setdefault('speed', '1.0')
        self.tts_args.setdefault('voice', 'filipp' if self.tts_args['lang'] == 'ru-RU' else 'nick')

        self.url = 'https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize'
        self.headers = {
            'Authorization': 'Bearer ' + iam_token,
        }
        self._data = {
            'folderId': folder_id
        }
        self._data.update(self.tts_args)

    def synthesize_chunk(self, text_chunk, chunk_folder, chunk_file_stem):
        chunk_path = chunk_folder.joinpath(chunk_file_stem + '.ogg')
        with chunk_path.open('wb') as f:
            for audio_content in self._synth(text_chunk):
                f.write(audio_content)
        return chunk_path

    def _synth(self, text):
        self._data['text'] = text
        with requests.post(self.url, headers=self.headers, data=self._data, stream=True) as resp:
            if resp.status_code != 200:
                raise RuntimeError("Invalid response received: code: %d, message: %s" % (resp.status_code, resp.text))
            for chunk in resp.iter_content(chunk_size=None):
                yield chunk


class GoogleTTS(TTSProvider):

    def __init__(self, ffmpeg=FFmpeg(), **kwargs):
        """
        Uses Google Text-to-speech API. See https://cloud.google.com/text-to-speech
        :param ffmpeg: ffmpeg tool to perform operations
        :param kwargs: HTTP-request parameters (see https://cloud.google.com/text-to-speech/docs/reference/rpc/google.cloud.texttospeech.v1#google.cloud.texttospeech.v1.VoiceSelectionParams)
        """
        super().__init__(ffmpeg)
        from google.cloud import texttospeech
        self.google_tts = texttospeech

        self.client = texttospeech.TextToSpeechClient()

        vsp = {
            'language_code': kwargs.get('language_code', 'en-US'),
            'ssml_gender': kwargs.get('ssml_gender', texttospeech.SsmlVoiceGender.MALE)
        }
        vsp['name'] = kwargs.get('name', vsp['language_code'] + '-Wavenet-A')
        self.voice = texttospeech.VoiceSelectionParams(**vsp)

        acp = {
            'audio_encoding': kwargs.get('audio_encoding', texttospeech.AudioEncoding.MP3),
            'speaking_rate': kwargs.get('speaking_rate', 1.0),
            'pitch': kwargs.get('pitch', 0.0),
            'volume_gain_db': kwargs.get('volume_gain_db', 0.0),
            'effects_profile_id': kwargs.get('effects_profile_id', []),
        }
        if 'sample_rate_hertz' in kwargs:
            acp['sample_rate_hertz'] = kwargs['sample_rate_hertz']
        self.audio_config = texttospeech.AudioConfig(**acp)

    def synthesize_chunk(self, text_chunk, chunk_folder, chunk_file_stem):
        chunk_path = chunk_folder.joinpath(chunk_file_stem + '.mp3')
        input_text = self.google_tts.SynthesisInput(text=text_chunk)
        response = self.client.synthesize_speech(
            request={"input": input_text, "voice": self.voice, "audio_config": self.audio_config}
        )
        # The response's audio_content is binary.
        with chunk_path.open("wb") as fh:
            fh.write(response.audio_content)
        return chunk_path

    @staticmethod
    def list_voices():
        from google.cloud import texttospeech
        """Lists the available voices."""
        client = texttospeech.TextToSpeechClient()
        # Performs the list voices request
        voices = client.list_voices()
        for voice in voices.voices:
            # Display the voice's name. Example: tpc-vocoded
            print(f"Name: {voice.name}")
            # Display the supported language codes for this voice. Example: "en-US"
            for language_code in voice.language_codes:
                print(f"Supported language: {language_code}")
            ssml_gender = texttospeech.SsmlVoiceGender(voice.ssml_gender)
            # Display the SSML Voice Gender
            print(f"SSML Voice Gender: {ssml_gender.name}")
            # Display the natural sample rate hertz for this voice. Example: 24000
            print(f"Natural Sample Rate Hertz: {voice.natural_sample_rate_hertz}\n")


if __name__ == "__main__":
    target = "texts/sample-ru.txt"
    ya_tts = YandexTTS(
        folder_id="folder-id",
        iam_token="iam-token",
        voice='alena',
        speed='0.95'
    )
    ya_tts.patterns_dict = {
            r'\bист\.': 'источник',
    }
    ya_tts.synthesize(target)

    target = "texts/sample-en.txt"
    go_tts = GoogleTTS(
        language_code='en-US',
        name='en-US-Wavenet-D',
        speaking_rate=0.9,
        pitch=8.0,
        volume_gain_db=3.0,
        effects_profile_id=[
            'medium-bluetooth-speaker-class-device',
            'handset-class-device'
        ]
    )
    go_tts.synthesize(target)
