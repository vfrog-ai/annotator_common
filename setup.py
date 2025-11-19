"""
Setup configuration for annotator_common package.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="annotator-common",
    version="0.2.6",
    author="vfrog",
    description="Common utilities and shared code for annotator services",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/vfrog-ai/annotator_common",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.11",
    install_requires=[
        "pymongo>=4.6.0",
        "aio-pika>=9.2.0",  # Keep for backward compatibility during migration
        "pydantic>=2.5.0",
        "google-cloud-storage>=2.14.0",
        "google-cloud-pubsub>=2.18.0",
        "elasticsearch>=8.11.0",
        "aiohttp>=3.9.0",  # For direct HTTP calls in LOCAL_MODE
    ],
)

