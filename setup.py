import os

from setuptools import find_packages, setup


try:
    with open(
        os.path.join(os.path.dirname(__file__), "README.md"), encoding="utf-8"
    ) as f:
        long_description = f.read()
except Exception:
    long_description = ""


cmdclass = {}


setup(
    name="pretix-ticketswap",
    version="1.0.1",
    description="TicketSwap integration for Pretix - enables secure ticket resale with SecureSwap technology",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/h3x4d3x4/Pretix-TicketSwap",
    author="Andre Vidal",
    author_email="andrei@hexadexa.dev",
    license="Apache",
    install_requires=[
        "requests>=2.32.0",
    ],
    packages=find_packages(exclude=["tests", "tests.*"]),
    include_package_data=True,
    cmdclass=cmdclass,
    entry_points="""
[pretix.plugin]
pretix_ticketswap=pretix_ticketswap
""",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Other Audience",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
)
