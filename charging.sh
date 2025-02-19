#!/bin/bash
tmux new-window -d -n 'charging' -t sess1:4 '$HOME/battbin/statusfilewatch.sh'
