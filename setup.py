from setuptools import find_packages, setup


setup(
    name="nba-agent",
    version="0.1.0",
    description="NBA daily info agent scaffold",
    packages=find_packages(),
    include_package_data=True,
    install_requires=["aiotieba>=4.6.1,<5"],
    entry_points={
        "console_scripts": [
            "nba-agent=nba_agent.app:main",
        ]
    },
)
