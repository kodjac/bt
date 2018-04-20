#!/bin/bash
alias git='git -c "http.proxy=$http_proxy"'

alias pull_submodules='git submodule foreach git -c "http.proxy=$http_proxy" pull'
