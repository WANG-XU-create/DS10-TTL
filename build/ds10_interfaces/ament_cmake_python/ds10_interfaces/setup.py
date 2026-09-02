from setuptools import find_packages
from setuptools import setup

setup(
    name='ds10_interfaces',
    version='0.1.0',
    packages=find_packages(
        include=('ds10_interfaces', 'ds10_interfaces.*')),
)
