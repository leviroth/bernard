from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='Bernard J. Ortcutt',

    version='0.4.0',

    description='Reddit moderation automated through reports',
    long_description=long_description,

    url='https://github.com/leviroth/bernard',

    author='Levi Roth',
    author_email='levimroth@gmail.com',

    license='MIT',

    classifiers=[
        'Development Status :: 4 - Alpha',
        'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ],

    keywords='reddit moderation',

    packages=find_packages(exclude=['contrib', 'docs', 'tests']),

    install_requires=['praw >=4.2, <5.0',
                      'pyyaml >=3.12, <4.0'],

    setup_requires=['pytest-runner >=2.1'],
    tests_require=['betamax >=0.8, <0.9',
                   'betamax-matchers >=0.3.0, <0.4',
                   'betamax-serializers >=0.2, <0.3',
                   'pytest >=2.7.3'],
    test_suite='pytest',
)
