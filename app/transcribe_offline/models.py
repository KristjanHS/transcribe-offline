"""Model pins. The only place model URLs, commits and hashes live."""

from dataclasses import dataclass

from transcribe_offline import APP_ROOT

MODELS_ROOT = APP_ROOT / "models"

# All mandatory: without tokenizer.json faster-whisper downloads a fallback tokenizer,
# without preprocessor_config.json it silently uses the wrong mel-bin count.
REQUIRED_FILES = (
    "model.bin",
    "config.json",
    "tokenizer.json",
    "vocabulary.json",
    "preprocessor_config.json",
)


@dataclass(frozen=True)
class ModelPin:
    repo: str
    commit: str
    subfolder: str  # "" = repo root
    files: dict[str, str]  # file name -> SHA-256 of the bytes served at url(name)

    def url(self, name: str) -> str:
        path = f"{self.subfolder}/{name}" if self.subfolder else name
        return f"https://huggingface.co/{self.repo}/resolve/{self.commit}/{path}"


# Keys are the language code and the folder under models/.
MODELS = {
    "et": ModelPin(
        repo="TalTechNLP/whisper-large-v3-turbo-et-verbatim",
        commit="1ae5a487d24116955803df4d9d01df56645eb44f",
        subfolder="ct2",
        files={
            "model.bin": "ca6b3ade047f141729de41324a5f8369e5e27374ab23d73a3d4bb1454e5c4f61",
            "config.json": "a0feddc18de0c285ed147e5483c8d1bc911bd45e23104ae0726d79594e7a6b1d",
            "tokenizer.json": "dfc530298b6fbed1a97c6472c575b026453706e2a204c7f7038f2c9d208b0759",
            "vocabulary.json": "07d24051798ca2a188f59bc350afc6d0cb947b25430c016bc8ed0a0854b11a8b",
            "preprocessor_config.json": (
                "654cf18d3e163b948ceaf9766da56ce0b52de265d58673cf61c9376f126bd499"
            ),
        },
    ),
    "en": ModelPin(
        repo="Systran/faster-distil-whisper-large-v3",
        commit="c3058b475261292e64a0412df1d2681c06260fab",
        subfolder="",
        files={
            "model.bin": "b79368e19b6623813609431a6e5ee309a71506701ebc49fd7820e692dec7c5f5",
            "config.json": "90c55f775cc4e0bb17293d0bf12f96557a486f20dea886fabd8e6075a3588b21",
            "tokenizer.json": "6d8cbd7cd0d8d5815e478dac67b85a26bbe77c1f5e0c6d76d1ce2abc0e5f21ca",
            "vocabulary.json": "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1",
            "preprocessor_config.json": (
                "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711"
            ),
        },
    ),
}
