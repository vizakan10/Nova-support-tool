from setuptools import setup, find_packages

setup(
    name="nova-cli",
    version="2.0.0",
    description="Nova CLI — support tool for collaborative error resolution",
    author="IFS",
    py_modules=["nova", "config", "kb_manager"],
    entry_points={
        "console_scripts": [
            "nova=nova:main",
        ],
    },
    install_requires=[
        "questionary>=2.0.0",
    ],
    python_requires=">=3.8",
    include_package_data=True,
    package_data={"": ["kb.json"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "Environment :: Console",
        "Topic :: Software Development :: Debuggers",
    ],
)
