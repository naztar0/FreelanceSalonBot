SHELL=/usr/bin/bash

all: update start

app:
	@nohup python -m app -O [UserFreelanceSalon] &

debug:
	@python -m app [UserFreelanceSalon] [DEBUG] &

start: app

update: install

install:
	@pip install -r requirements.txt

.PHONY: all app start update install
