#!/bin/bash
ps aux | grep chrome | grep user-data-dir | grep -v grep | awk '{print $2}' | head -3
