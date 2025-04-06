from setuptools import find_packages, setup

package_name = 'web_api'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'fastapi','uvicorn', 'websockets'],
    zip_safe=True,
    maintainer='mcalec',
    maintainer_email='mcalec9999@gmail.com',
    description='ROS2 FastAPI Bridge',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'web_api = web_api.web_api:main'
        ],
    },
)
