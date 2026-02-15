from setuptools import setup, find_packages

setup(
    name="viza-wsl",
    version="1.0.0",
    description="WSL Terminal Error Capture Tool",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    py_modules=['wsl_terminal_reader'],
    entry_points={
        'console_scripts': [
            'viza=wsl_terminal_reader:main',
        ],
    },
    install_requires=[],
    python_requires='>=3.6',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
    ],
)
