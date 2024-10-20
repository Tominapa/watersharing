"""
This method allows the user to request drive distances and drive times using Bing maps API and
Open Street Maps API. 
The method accept the following input arguments:
- origin:   REQUIRED. Data containing information regarding location name, and coordinates
            latitude and longitude. Two formats are acceptable:
            {(origin1,"latitude"): value1, (origin1,"longitude"): value2} or
            {origin1:{"latitude":value1, "longitude":value2}}
            The first format allows the user to include a tab with the corresponding data
            in a table format as part of the workbook casestudy.

- destination:  OPTIONAL. If no data for destination is provided, it is assumed that the
                origins are also destinations.

- api:  OPTIONAL. Specify the type of API service, two options are supported:
            Bing maps: https://docs.microsoft.com/en-us/bingmaps/rest-services/
            Open Street Maps: https://www.openstreetmap.org/
            If no API is selected, Open Street Maps is used by default

- api_key:  An API key should be provided in order to use Bing maps. The key can be obtained at:
            https://www.microsoft.com/en-us/maps/create-a-bing-maps-key

- output:   OPTIONAL. Define the paramters that the method will output. The user can select:
            'time': A list containing the drive times between the locations is returned
            'distance': A list containing the drive distances between the locations is returned
            'time_distance': Two lists containing the drive times and drive distances betweent
            the locations is returned
            If not output is specified, 'time_distance' is the default

- fpath:    OPTIONAL. od_matrix() will ALWAYS output an Excel workbook with two tabs, one that
            contains drive times, and another that contains drive distances. If not path is
            specified, the excel file is saved with the name 'od_output.xlsx' in the current
            directory.

- create_report OPTIONAL. if True an Excel report with drive distances and drive times is created
"""


import pandas as pd
import numpy as np
import requests
import json

from Utilities import df_to_dict_helper


def get_driving_distance(distance_JSON, DF_PRODUCER, DF_CONSUMER):
    """
    distance_JSON - directory to distance JSON file
    DF_PRODUCER - Producer dataframe
    DF_CONSUMER - Consumer dataframe
    """
    origin = DF_PRODUCER.set_index(["WellpadUnique"]).T.to_dict()
    destination = DF_CONSUMER.set_index(["WellpadUnique"]).T.to_dict()

    origins_loc = []
    destination_loc = []
    origins_dict = {}
    destination_dict = {}

    api = "open_street_map"
    api_key = None
    output = "time_distance"

    create_report = True

    # Check that a valid API service has been selected and make sure an api_key was provided
    if api in ("open_street_map", None):
        api_url_base = "https://router.project-osrm.org/table/v1/driving/"

    elif api == "bing_maps":
        api_url_base = "https://dev.virtualearth.net/REST/v1/Routes/DistanceMatrix?"
        if api_key is None:
            raise Warning("Please provide a valid api_key")
    else:
        raise Warning("{0} API service is not supported".format(api))

    # =======================================================================
    #                          PREPARING DATA FORMAT
    # =======================================================================
    # Check if the input data has a Pyomo format:
    #   origin={(origin1,"latitude"): value1, (origin1,"longitude"): value2}
    # if it does, the input is modified to a Dict format:
    #   origin={origin1:{"latitude":value1, "longitude":value2}}
    if isinstance(list(origin.keys())[0], tuple):
        for i in list(origin.keys()):
            origins_loc.append(i[0])
        origins_loc = list(sorted(set(origins_loc)))

        for i in origins_loc:
            origins_dict[i] = {
                "latitude": origin[i, "Latitude"],
                "longitude": origin[i, "Longitude"],
            }
        origin = origins_dict

    if isinstance(list(destination.keys())[0], tuple):
        for i in list(destination.keys()):
            destination_loc.append(i[0])
        destination_loc = list(sorted(set(destination_loc)))

        for i in destination_loc:
            destination_dict[i] = {
                "latitude": destination[i, "Latitude"],
                "longitude": destination[i, "Longitude"],
            }
        destination = destination_dict

    # =======================================================================
    #                           SELECTING API
    # =======================================================================

    if api in (None, "open_street_map"):
        # This API works with GET requests. The general format is:
        # https://router.project-osrm.org/table/v1/driving/Lat1,Long1;Lat2,Long2?sources=index1;index2&destinations=index1;index2&annotations=[duration|distance|duration,distance]
        coordinates = ""
        origin_index = ""
        destination_index = ""
        # Building strings for coordinates, source indices, and destination indices
        for index, location in enumerate(origin.keys()):
            coordinates += (
                str(origin[location]["Longitude"])
                + ","
                + str(origin[location]["Latitude"])
                + ";"
            )
            origin_index += str(index) + ";"

        for index, location in enumerate(destination.keys()):
            coordinates += (
                str(destination[location]["Longitude"])
                + ","
                + str(destination[location]["Latitude"])
                + ";"
            )
            destination_index += str(index + len(origin)) + ";"

        # Dropping the last character ";" of each string so the API get request is valid
        coordinates = coordinates[:-1]
        origin_index = origin_index[:-1]
        destination_index = destination_index[:-1]
        response = requests.get(
            api_url_base
            + coordinates
            + "?sources="
            + origin_index
            + "&destinations="
            + destination_index
            + "&annotations=duration,distance"
        )
        response_json = response.json()

        df_times = pd.DataFrame(
            index=list(origin.keys()), columns=list(destination.keys())
        )
        df_distance = pd.DataFrame(
            index=list(origin.keys()), columns=list(destination.keys())
        )
        output_times = {}
        output_distance = {}

        # Loop for reading the output JSON file
        if response_json["code"].lower() == "ok":
            for index_i, o_name in enumerate(origin):
                for index_j, d_name in enumerate(destination):

                    output_times[(o_name, d_name)] = (
                        response_json["durations"][index_i][index_j] / 3600
                    )
                    output_distance[(o_name, d_name)] = (
                        response_json["distances"][index_i][index_j] / 1000
                    ) * 0.621371

                    df_times.loc[o_name, d_name] = output_times[(o_name, d_name)]
                    df_distance.loc[o_name, d_name] = output_distance[(o_name, d_name)]
        else:
            raise Warning("Error when requesting data, make sure your API key is valid")

    elif api == "bing_maps":
        # Formating origin and destination dicts for Bing Maps POST request, that is, converting this structure:
        # origin={origin1:{"latitude":value1, "longitude":value2},
        #           origin2:{"latitude":value3, "longitude":value4}}
        # destination={destination1:{"latitude":value5, "longitude":value6,
        #               destination2:{"latitude":value7, "longitude":value8}}
        # Into the following structure:
        # data={"origins":[{"latitude":value1, "longitude":value2},
        #                   {"latitude":value3, "longitude":value4}],
        #       "destinations":[{"latitude":value5, "longitude":value6},
        #                       {"latitude":value7, "longitude":value8}]}

        origins_post = []
        destinations_post = []
        for i in origin.keys():
            origins_post.append(
                {"latitude": origin[i]["Latitude"], "longitude": origin[i]["Longitude"]}
            )

        for i in destination.keys():
            destinations_post.append(
                {"latitude": origin[i]["Latitude"], "longitude": origin[i]["Longitude"]}
            )

        # Building the dictionary with the adequate structure compatible with Bing Maps
        data = {
            "origins": origins_post,
            "destinations": destinations_post,
            "travelMode": "driving",
        }

        # Sending a POST request to the API
        header = {"Content-Type": "application/json"}
        response = requests.post(
            api_url_base + "key=" + api_key, headers=header, json=data
        )
        response_json = response.json()

        # Definition of two empty dataframes that will contain drive times and distances.
        # These dataframes wiil be exported to an Excel workbook
        df_times = pd.DataFrame(
            index=list(origin.keys()), columns=list(destination.keys())
        )
        df_distance = pd.DataFrame(
            index=list(origin.keys()), columns=list(destination.keys())
        )
        output_times = {}
        output_distance = {}

        # Loop for reading the output JSON file
        if response_json["statusDescription"].lower() == "ok":
            for i in range(
                len(response_json["resourceSets"][0]["resources"][0]["results"])
            ):
                data_temp = response_json["resourceSets"][0]["resources"][0]["results"][
                    i
                ]
                origin_index = data_temp["originIndex"]
                destination_index = data_temp["destinationIndex"]

                o_name = list(origin.keys())[origin_index]
                d_name = list(destination.keys())[destination_index]
                output_times[(o_name, d_name)] = data_temp["travelDuration"] / 60
                output_distance[(o_name, d_name)] = (
                    data_temp["travelDistance"] * 0.621371
                )

                df_times.loc[o_name, d_name] = output_times[(o_name, d_name)]
                df_distance.loc[o_name, d_name] = output_distance[(o_name, d_name)]
        else:
            raise Warning("Error when requesting data, make sure your API key is valid")

    if create_report is True:
        # Dataframes df_times and df_distance are output as dictionaries in JSON format whose directory
        # and name are defined by variable 'distance_JSON'
        # df_times_dict = df_to_dict_helper(df_times)
        df_times_dict = df_times.transpose().to_dict(orient="index")
        # df_distance_dict = df_to_dict_helper(df_distance)
        df_distance_dict = df_distance.transpose().to_dict(orient="index")
        with open(distance_JSON, "w") as data_file:
            json.dump(
                {"DriveTimes": df_times_dict, "DriveDistances": df_distance_dict},
                data_file,
                indent=2,
            )

    # Identify what type of data is returned by the method
    if output in ("time", None):
        print("Time data retrieved")
    elif output == "distance":
        print("Distance data retrieved")
    elif output == "time_distance":
        print("Time and distance data retrieved")
    else:
        raise Warning(
            "Provide a valid type of output, valid options are:\
                        time, distance, time_distance"
        )

    return df_times, df_distance
