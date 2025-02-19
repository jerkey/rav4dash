#!/bin/bash
kill $(pgrep -f statusfilewatch.sh)
exit
debian   30175  1.9  0.4   7048  2380 pts/8    Ss+  19:07   0:48 bash -c $HOME/battbin/statusfilewatch.sh
