from setuptools import setup
from setuptools.command.install import install


class PostInstall(install):
    """Print setup instructions after install (smooth install flow)."""
    def run(self):
        install.run(self)
        msg = """
  Nova CLI installed successfully.
  Run:  nova   or  nova help   (setup will be offered if not configured).
  If 'nova' not found, add to PATH:  export PATH="$HOME/.local/bin:$PATH"
  Then run:  nova setup   to set KB path and AI provider.
"""
        print(msg)


setup(
    name="nova-cli",
    version="2.0.0",
    description="Nova CLI — support tool for collaborative error resolution",
    author="IFS",
    py_modules=["nova_cli", "config", "kb_manager"],
    entry_points={
        "console_scripts": [
            "nova=nova_cli:main",
        ],
    },
    install_requires=[
        "questionary>=2.0.0",
    ],
    python_requires=">=3.8",
    include_package_data=True,
    package_data={"": ["kb.json"]},
    cmdclass={"install": PostInstall},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "Environment :: Console",
        "Topic :: Software Development :: Debuggers",
    ],
)
