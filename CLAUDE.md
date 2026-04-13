## Project
The objective of this project is to make a demonstration of AstraeaDB (/Users/jimharris/Documents/astraeadb) that demonstrates how it could be used in theory with a data lake to improve retrieval of data. It should use some of the same hybrid search capabilities displayed in the GraphRAG demo at /Users/jimharris/Documents/graphrag-demo and the cyber graph demo at /Users/jimharris/Documents/cyber-graph-demo

Today, large corporations store massive amounts of data in data lakes in various formats: some might be in JSON structures, others in CSVs, other sources as parquet or delta files. Many of the data sources might contain different perspectives on the same event, such as a web application firewall showing a connection from a client at the same time the application's authentication logs show a sign on from that customer. Other types of logs may show the same general type of data at differnt times. For example, a company might use Microsoft Teams for video conferencing for a few years, and then switch to Zoom, so the logs from Teams and Zoom both describe calls that happened, but would cover different periods of times and have different formats. The company might keep all of these logs in their lake, but have no practical way to use them because they can't use a central tool to query all of them, and there's no easy way to use something like an LLM to answer questions about all of the data.

We're going to show how AstraeaDB could keep all of the metadata about the various data sources--semantic embeddings describing the nature of the data source, information about the format of the data, and connections to all of the elements within the data (column names, field names, etc.) and enable a chatbot to find and use the data. Essentially, AstraeaDB would enable the LLM to answer questions like "how has the number of video calls changed since the Pandemic?" because it would tell the LLM where to find video call information in the years since the Pandemic, what format it's in, so the LLM would know what tools to read the original data and how to put the elements together to give the answer.

## The initial task

Building and using whatever subagents or agent teams are necessary, research and develop a plan to construct this demo. Come up with ideas and evidence to answer the following questions:

* Should the demo use open source data sets, or create synthetic data?
* How will the demo segregate the data to simulate the fragmentation of an Enterprise data lake without having an overwhelming amount of data for our small demo?
* What types of data sources should we use to show temporal connections for the same type of source as well as multi-perspective data sets for the same event?
* How can we effectively show this capabilities?

Create a markdown document with ideas and development questions for me to answer in-line. After the questions are all answered and the task is well-understood, we'll create an implementation plan.

