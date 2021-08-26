import os

from setuptools import find_packages, setup


with open(os.path.join("osgithub", "VERSION")) as f:
    version = f.read().strip()

setup(
    name="osgithub",
    version=version,
    packages=find_packages(exclude=["tests"]),
    url="https://github.com/opensafely-core/osgithub",
    author="OpenSAFELY",
    author_email="tech@opensafely.org",
    python_requires=">=3.7",
    install_requires=["requests", "requests-cache", "furl"],
    entry_points={},
    include_package_data=True,
    classifiers=["License :: OSI Approved :: GNU General Public License v3 (GPLv3)"],
)
