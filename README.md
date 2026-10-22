#Arte Voyages – AI/ML Use Cases for Luxury Travel and Tourism

#Project Overview

This repository contains AI/ML prototypes and technical documentation developed for Arte Voyages, a luxury travel and tourism initiative focused on personalised travel experiences for high-net-worth individuals (HNIs) visiting South Asia.
The project explores itinerary intelligence, hotel rate prediction, multilingual inquiry processing, trip risk monitoring, and partner confirmation prediction to support travel planning and trip operations.

#Project Modules

#Part 1: Itinerary Compatibility and Redundancy — Akanksha

1.1 Multi-Country Itinerary Compatibility Checker

Validates destination sequences and route feasibility.
Identifies unnecessary backtracking, travel-time constraints, connection issues, visa requirements, and seasonal closures.

1.2 Itinerary Redundancy Detector

Compares proposed itineraries with previous travel history and preferences.
Detects similar activities and classifies them as Green, Yellow, or Red to help admins manage repetitions.

#Part 2: Hotel Rate and Inquiry Extraction — Harsha

2.1 Hotel Rate Prediction and Demand Analysis

Estimates reference nightly hotel rates using historical booking data.
Analyses rate patterns and potential demand indicators.

2.2 Multilingual Travel Inquiry Information Extractor

Extracts structured travel requirements from English, French, and German customer inquiries.
Highlights supporting text and identifies missing or ambiguous information.

Part 3: Trip Risk Monitoring and Partner Prediction — Charanjeeth

3.1 Continuous Trip Risk Monitoring

Monitors relevant travel advisories, hazard alerts, and news for booked trips.
Scores potential risks and generates Green, Watch, or Act alerts.

3.2 Partner Confirmation Prediction and Sequencing

Estimates partner confirmation outcomes, including confirmed, declined, and no reply.
Uses booking dependencies and predicted reliability to prioritise requests and backup arrangements.

#Technologies

Depending on the use case, the project uses:
Python
Pandas and NumPy
Scikit-learn
Sentence Transformers and NLP
FastAPI
PostgreSQL
Streamlit
Plotly and Matplotlib
Git and GitHub
Additional libraries and data sources are selected according to individual module requirements.
