SHELL=/usr/bin/bash

all: update start

app:
	@nohup python -m app -O [FreelanceSalon] &

debug:
	@nohup python -m app [FreelanceSalon] [DEBUG] &

start: app

update: install

install:
	@pip install -r requirements.txt

.PHONY: all app start update install
