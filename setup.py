#!/usr/bin/env python3
#
# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import distutils.util
import setuptools
import os

version = "0.2.3"

with open("requirements.txt") as f:
    requirements = [ln.split("#")[0].rstrip() for ln in f.readlines()]

setuptools.setup(
    name="loop_tool_service",
    version=version,
    description="Example code for CompilerGym",
    author="Facebook AI Research",
    url="https://github.com/facebookresearch/CompilerGym",
    license="MIT",
    install_requires=requirements,
    packages=[
        "loop_tool_service",
        "loop_tool_service.service_py",
        "loop_tool_service.service_py.datasets",
        "loop_tool_service.service_py.rewards",
        "loop_tool_service.benchmarks",        
    ],
    python_requires=">=3.8",
    platforms=[distutils.util.get_platform()],
    zip_safe=False,
)

# vi3: Install by using this command.
# python -m pip install .
# According to this: https://stackoverflow.com/questions/66125129/unknownextra-error-when-installing-via-setup-py-but-not-via-pip


###############################################################
# Set up root directory
###############################################################
print("\nSet root directory: \n\nexport LOOP_TOOL_ROOT=%s"%os.getcwd())
print("\n")
