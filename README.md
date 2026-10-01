```markdown
# DNS Caching Server

A Python-based DNS caching client-server application developed as part of a Computer Networks course.

## Project Overview

The project implements a DNS caching server that receives requests from a client, resolves domain names using DNS, and stores results in a local cache to improve response time and reduce repeated DNS queries.

The server uses UDP communication and supports TTL-based caching and LRU cache replacement.

## Features

- DNS resolution using `dnspython`
- UDP client-server communication
- TTL-based DNS caching
- LRU cache replacement using `OrderedDict`
- Cache inspection and clearing
- RTT measurement
- DNS request and response handling
- Support for networking protocol analysis

## Technologies

- Python
- UDP Sockets
- DNS
- dnspython
- OrderedDict
- TTL Caching
- LRU Cache
- Wireshark

## Project Structure

```text
dns-caching-server/
├── dns_cache_server.py
├── dns_client.py
├── dns_cache.txt
├── requirements.txt
└── README.md
```
## How It Works
The project follows a client-server architecture.
1. The client sends a DNS resolution request to the server using UDP.
2. The server checks whether the requested DNS record already exists in the local cache.
3. If a valid cached result exists, the server returns it directly to the client.
4. If the record is not available in the cache, the server performs a DNS lookup using dnspython.
5. The result is stored in the cache together with its TTL.
6. When the cache reaches its limit, the Least Recently Used (LRU) entry is removed.
## Installation
1. Clone the repository
git clone https://github.com/yarajaber70/dns-caching-server.git

2. Enter the project directory
cd dns-caching-server

3. Install dependencies
pip install -r requirements.txt

## How to Run
1. Start the DNS caching server
python dns_cache_server.py

2. Start the client
Open another terminal and run:
python dns_client.py

The client can then send requests to the DNS caching server.
Caching Mechanism
The server uses a local cache to reduce unnecessary DNS lookups.
Each cached DNS record includes a TTL value. Once the TTL expires, the record is no longer considered valid.
The cache also uses an LRU (Least Recently Used) replacement policy implemented with Python's OrderedDict.
Networking Concepts
This project demonstrates practical use of:
- DNS
- UDP
- Client-server communication
- Socket programming
- TTL
- Caching
- LRU replacement
- Round-Trip Time (RTT)
- Network protocol analysis
Learning Outcomes
Through this project, I gained hands-on experience with:
- Implementing UDP socket communication in Python
- Working with DNS requests and responses
- Building a TTL-based caching mechanism
- Implementing LRU cache replacement
- Measuring network response times
- Debugging network communication
- Analyzing DNS traffic using Wireshark
Author
Yara Jaber
B.Sc. Information Systems Student
University of Haifa
