# yago-tts
Скрипт, использующий API Яндекс и Google для озвучки текстовых файлов (синтез речи).

Перед использованием необходимо выполнить установку соответствующих сервисов и аккаунтов, как описано в документациях.

Скрипт использует [FFmpeg](https://ffmpeg.org/) для обработки аудио-файлов.
## Яндекс SpeechKit
### Пример
```python
target = "texts/sample-ru.txt"
ya_tts = YandexTTS(
    folder_id="your_folder_id",
    iam_token="your_iam_token",
    voice='alena',
    speed='0.95'
)
ya_tts.synthesize(target)
```
### Установка
[Документация Яндекс SpeechKit](https://cloud.yandex.ru/docs/speechkit/tts/)

Список голосов Яндекс: [Список голосов](https://cloud.yandex.ru/docs/speechkit/tts/voices) 
## Google
### Пример
```python
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
```
### Установка
[Документация Google Text-to-Speech](https://cloud.google.com/text-to-speech/docs/quickstart-client-libraries)

Список голосов Google TTS: [Список голосов](https://cloud.google.com/text-to-speech/docs/voices)
