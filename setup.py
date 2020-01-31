#!/usr/bin/env python3

import setuptools
import subprocess

long_description = open("README.md").read()

try:
    commit_count = subprocess.check_output(["git", "rev-list", "--count", "HEAD"]).decode("utf-8").strip()
except Exception:
    commit_count = "git-commit-count-error"

setuptools.setup(
    name                          = 'il',
    version                       = '0.' + commit_count,
    author                        = 'Antti Kervinen',
    author_email                  = 'antti.kervinen@gmail.com',
    description                   = 'Inline assembly in Python',
    long_description              = long_description,
    long_description_content_type = 'text/markdown',
    url                           = 'https://github.com/askervin/python-il',
    py_modules                    = ['il'],
    packages                      = [],
    package_data                  = {},
    scripts                       = [],
    classifiers                   = [
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
