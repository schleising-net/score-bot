#!/bin/zsh
docker rm --force score-bot
docker run --name score-bot score-bot-image
