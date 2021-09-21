from setuptools import setup

with open("README.md", 'r') as f:
    long_description = f.read()

setup(
   name='replacements',
   version='1.0',
   description='Replace strings with other strings',
   license="MIT",
   long_description=long_description,
   author='Dror Speiser',
   url="http://github.com/drorspei/replacements",
   py_modules=['replacements']
)
