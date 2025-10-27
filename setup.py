from setuptools import setup, find_packages

setup(
    name="parser_2gis",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pychrome",
        "requests",
        "psutil",
        "pydantic",
    ],
    entry_points={
        'console_scripts': [
            'parser_2gis=main:cli_app',
        ],
    },
)