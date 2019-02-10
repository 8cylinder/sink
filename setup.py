
from setuptools import setup

import sys
import platform
import re

version = re.search(
    "^__version__\s*=\s*'(.*)'",
    open('sink/sink.py').read(),
    re.M
).group(1)

if sys.version_info.major == 2 or (sys.version_info.major == 3 and sys.version_info.minor < 6):
    dividers = '!' * 40
    sys.exit("{}\nSorry, sink does not support python lower that 3.6.\n{}".format(dividers, dividers))

long_description = """Sink is a command line tool that helps with common tasks for websites."""

setup(
    name='sink',
    packages=[
        'sink'
    ],
    # packages_data={
    #     'sink': []
    # }
    entry_points='''
        [console_scripts]
        sink=sink.sink:sink
    ''',
    install_requires=[
        'click', 'PyYAML'
    ],
    version=version,
    description=long_description,
    long_description=long_description,
    url='https://github.com/8cylinder/sink',
)
# build source dist and wheel:
#   python3 setup.py sdist bdist_wheel
# upload to pypi:
#   twine upload dist/*
# install for dev:
#    pip install --user --editable .
