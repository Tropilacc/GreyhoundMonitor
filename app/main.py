DOG_NAME = "Fast Fred"

INITIALPRICE = 4.60

CURRENTPRICE = 10.80

if INITIALPRICE < 5 and CURRENTPRICE > 10:

    print("********************************")
    print("ALERT")
    print(DOG_NAME)
    print("Initial:", INITIALPRICE)
    print("Current:", CURRENTPRICE)
    print("********************************")

else:

    print("No alert")