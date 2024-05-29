FROM centos/python-36-centos7

USER root

COPY . /san-exporter

WORKDIR /san-exporter

#RUN yum install -y python3-setuptools

# Need to upgrade pip due to package cryptography - the requeriment of paramiko
#   link: https://github.com/Azure/azure-cli/issues/16858
RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host=files.pythonhosted.org --upgrade pip 
#RUN python3 -m pip install --upgrade pip

RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host=files.pythonhosted.org -U pip setuptools

RUN pip3 install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host=files.pythonhosted.org -r requirements.txt

ENTRYPOINT [ "python" ]

CMD [ "manage.py" ]
