from setuptools import find_packages, setup


setup(
    name="web-to-podcast",
    version="0.1.0",
    description="Crawl web resources, translate with local Gemma/Ollama, and render podcast audio with VibeVoice.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.9",
    package_dir={"": "src"},
    packages=find_packages("src"),
    install_requires=["PyYAML>=6.0"],
    extras_require={
        "tts": ["numpy>=1.24", "soundfile>=0.12", "torch>=2.2"],
        "asr": ["openai-whisper>=20231117"],
        "browser": ["playwright>=1.45"],
        "dev": ["pytest>=8.0"],
    },
    entry_points={"console_scripts": ["web-to-podcast=web_to_podcast.cli:main"]},
)
