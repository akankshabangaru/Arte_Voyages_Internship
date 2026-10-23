#This is only starter code to verify that the itinerary input works; it does not yet validate real flight routes, visas, travel times, or seasonal closures.
def check_itinerary(destinations):
    """
    Basic starter function to review a proposed itinerary.
    """
    if not destinations:
        return "No destinations provided."

    if len(destinations) < 2:
        return "Add at least two destinations to review the itinerary."

    return f"Itinerary received: {' -> '.join(destinations)}"


if __name__ == "__main__":
    itinerary = ["Delhi", "Mumbai", "Sri Lanka"]
    print(check_itinerary(itinerary))
