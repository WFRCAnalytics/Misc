
import os
import arcpy
import geopandas as gpd
import pandas as pd

#================
# functions
#================

def getFieldNames(fc3):
    keepfields = ["PopDens2018", "JobDens2018", "lumixscore", "K12Schoolsdist", "ParksTrailheadsdist", "collegedist", "RetailCentersdist", "busdist", "RailStationsdist",
                  "B01001_calc_pctDependE", "B17020_calc_pctPovE", "B08201_calc_pctNoVehE", "BlockLength", "MeanBikeRating", "MeanPedRating", "zone_id", "area_sqm",
                  "Shape_Area", "OBJECTID_1", "Shape_Length", "Shape"]
    removefields = [f.name for f in arcpy.ListFields(fc3) if f.name not in keepfields]
    return removefields

def MultiRing_Buffer(in_shapefile, out_shapefile, distance_list, field_name="distance"):
        
    # read in shapefile as dataframe
    features = gpd.read_file(in_shapefile)
    
    # order distance list from greatest to least and get length
    distances_g2l = sorted(distance_list, reverse=True)
    number_of_rings = len(distance_list) 
    
    # initialize some constants
    dissolved_features = None
    prev_dissolved_features_df = None
    previous_distance = None
    index = 0
    merge_list = []
    
    # loop thru distances
    for distance in distances_g2l:
        
        print("Buffering to {}...".format(distance))
        
        # buffer data
        buffered_feature = features.buffer(distance)
        buffered_feature_df = gpd.GeoDataFrame(crs=features.crs, geometry=buffered_feature)
        
        # if last
        if index == (number_of_rings - 1):
           buffered_feature_df[field_name] = distance
        
        # Add dummy buffer field and dissolve
        buffered_feature_df['dissolve'] = 1
        dissolved_features = buffered_feature_df.dissolve(by='dissolve')
        
        # remove unused features from memory
        del buffered_feature
        del buffered_feature_df
        
        # if not first ring
        if index > 0:
            
            # add distance field value
            prev_dissolved_features_df[field_name] = previous_distance
            
            # compute and append difference
            difference = gpd.overlay(prev_dissolved_features_df, dissolved_features, how='difference')
            merge_list.append(difference)
            del difference
            
            # most inner ring wont need to be differenced, add to list
            if index == (number_of_rings - 1):
                dissolved_features[field_name] = distance
                merge_list.append(dissolved_features)
                
                
        # increment the index and manage constants
        prev_dissolved_features_df = dissolved_features
        del dissolved_features
        previous_distance = distance
        index += 1
    
    # Convert paths to dataframes and merge the geometries
    print('Merging features...')
    print(merge_list)
    merged_features = gpd.GeoDataFrame(pd.concat(merge_list, ignore_index=True), crs=merge_list[0].crs)
    merged_features.to_file(out_shapefile)
    
    # return path to output file
    print('Multi-ring buffer done!')
    return out_shapefile


#================
# main
#================

#set working directory
wd = r"C:\LocalGIS\LatentDemand2020\DemandPolygon_Inputs.gdb"
temp_wd = os.path.dirname(wd)
arcpy.env.workspace = wd
arcpy.env.overwriteOutput = True

#list feature classes
fclist = arcpy.ListFeatureClasses()
print(fclist)


#Buffers
bufferslist1 = ["RailStations", "K12Schools", "ParksTrailheads", "RetailCenters"]
for i in bufferslist1:
    arcpy.MultipleRingBuffer_analysis(i, i+"buffer", [330, 660, 1320, 2640, 150000], "feet", i+"dist", "ALL")
    print(i+"Complete!")

arcpy.MultipleRingBuffer_analysis("Colleges", "CollegesBuffer", [1, 2, 4, 100], "miles", "collegedist", "ALL")

#prep bus data for buffer
bus_distances = [330, 660, 1320, 2640, 100000]
bus_distances_meters = [distance*0.3048 for distance in bus_distances]
arcpy.FeatureClassToFeatureClass_conversion("BusStops", temp_wd, "bus_stops.shp")
bus_buffer = MultiRing_Buffer(os.path.join(temp_wd, "bus_stops.shp"), os.path.join(temp_wd, "BusStopsBuffer.shp"), bus_distances_meters, "busdist")
arcpy.FeatureClassToFeatureClass_conversion(bus_buffer, wd, "BusStopsBuffer")




# Calc Densities
print('Calculating densities...')
codeblock = """
def CalcDensity(amount, area):
    if area != 0:
        return amount/area
    else:
        return 0
"""
arcpy.AddField_management("PopTAZ", "PopDens2018", "DOUBLE")
arcpy.CalculateField_management("PopTAZ", "PopDens2018", ("CalcDensity(!YEAR2018!,!DEVACRES!)"), "PYTHON3", codeblock)

arcpy.AddField_management("JobsTAZ", "JobDens2018", "DOUBLE")
arcpy.CalculateField_management("JobsTAZ", "JobDens2018", ("CalcDensity(!YEAR2018!,!DEVACRES!)"), "PYTHON3", codeblock)

# Calc block length
print('Calculating block length...')
arcpy.AddField_management("Roads", "BlockLength", "DOUBLE")
arcpy.CalculateGeometryAttributes_management("Roads", [["BlockLength", "LENGTH"]], "FEET_US", '')

# Calc Bike and Ped Facility Ratings

print('Calculating bike and ped facility ratings...')
arcpy.AddField_management("RoadsWithPathways", "BikeLRating", "LONG")
arcpy.AddField_management("RoadsWithPathways", "BikeRRating", "LONG")
arcpy.AddField_management("RoadsWithPathways", "PedLRating", "LONG")
arcpy.AddField_management("RoadsWithPathways", "PedRRating", "LONG")
arcpy.AddField_management("RoadsWithPathways", "MeanBikeRating", "DOUBLE")
arcpy.AddField_management("RoadsWithPathways", "MeanPedRating", "DOUBLE")


bikefc = "RoadsWithPathways"

fieldsL = ["BIKE_L", "BikeLRating"]
with arcpy.da.UpdateCursor(bikefc, fieldsL) as cursor:
    for row in cursor:
        if (row[0] == "1A" or row[0] == "1B" or row[0] == "1C" or row[0] == "PP"):
            row[1] = 100
        elif (row[0] == "2A" or row[0] == "2B"):
            row[1] = 66
        elif (row[0] == "3" or row[0] == "3A" or row[0] == "3B" or row[0] == "3C"):
            row[1] = 33
        else:
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row

fieldsR = ["BIKE_R", "BikeRRating"]
with arcpy.da.UpdateCursor(bikefc, fieldsR) as cursor:
    for row in cursor:
        if (row[0] == "1A" or row[0] == "1B" or row[0] == "1C" or row[0] == "PP"):
            row[1] = 100
        elif (row[0] == "2A" or row[0] == "2B"):
            row[1] = 66
        elif (row[0] == "3" or row[0] == "3A" or row[0] == "3B" or row[0] == "3C"):
            row[1] = 33
        else:
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row


fieldsPedL = ["PED_L", "PedLRating"]
with arcpy.da.UpdateCursor(bikefc, fieldsPedL) as cursor:
    for row in cursor:
        if (row[0] == "Sidewalk" or row[0] == "Trail"):
            row[1] = 100
        elif (row[0] == None):
            row[1] = 0
        else:
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row

fieldsPedR = ["PED_R", "PedRRating"]
with arcpy.da.UpdateCursor(bikefc, fieldsPedR) as cursor:
    for row in cursor:
        if (row[0] == "Sidewalk" or row[0] == "Trail"):
            row[1] = 100
        elif (row[0] == None):
            row[1] = 0
        else:
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row


meanbikefields = ["BikeLRating", "BikeRRating", "MeanBikeRating"]
with arcpy.da.UpdateCursor(bikefc, meanbikefields) as cursor:
    for row in cursor:
        row[2] = ((row[0]+row[1])/2)
        cursor.updateRow(row)
    del cursor, row

meanpedfields = ["PedLRating", "PedRRating", "MeanPedRating"]
with arcpy.da.UpdateCursor(bikefc, meanpedfields) as cursor:
    for row in cursor:
        row[2] = ((row[0]+row[1])/2)
        cursor.updateRow(row)
    del cursor, row


# Spatial Join all variables to polygon features
print('Running spatial joins...')
zones = "microzones_04292020"

# Create empty field mappings table, then all fields from both tables
fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable(zones)
fieldmappings.addTable("PopTAZ")

# Get the index of the PopDens2018 from fieldmappings table
popDens2018FieldIndex = fieldmappings.findFieldMapIndex("PopDens2018")
fieldmap = fieldmappings.getFieldMap(popDens2018FieldIndex)

# Change merge rule of PopsDens2018 field
fieldmap.mergeRule = "mean"

# Replace old PopDens2018 field the new modified one
fieldmappings.replaceFieldMap(popDens2018FieldIndex, fieldmap)

arcpy.SpatialJoin_analysis(zones, "PopTAZ", "ZonesJoin1", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin1")
fieldmappings.addTable("JobsTAZ")
jobdens2018fieldindex = fieldmappings.findFieldMapIndex("JobDens2018")
fieldmap = fieldmappings.getFieldMap(jobdens2018fieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(jobdens2018fieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin1", "JobsTAZ", "ZonesJoin2", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin2")
fieldmappings.addTable("LandUseMixIndex")
lumixfieldindex = fieldmappings.findFieldMapIndex("lumixscore")
fieldmap = fieldmappings.getFieldMap(lumixfieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(lumixfieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin2", "LandUseMixIndex", "ZonesJoin3", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin3")
fieldmappings.addTable("K12Schoolsbuffer")
schoolsfieldindex = fieldmappings.findFieldMapIndex("K12Schoolsdist")
fieldmap = fieldmappings.getFieldMap(schoolsfieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(schoolsfieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin3", "K12Schoolsbuffer", "ZonesJoin4", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin4")
fieldmappings.addTable("ParksTrailheadsbuffer")
parksfieldindex = fieldmappings.findFieldMapIndex("ParksTrailheadsdist")
fieldmap = fieldmappings.getFieldMap(parksfieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(parksfieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin4", "ParksTrailheadsbuffer", "ZonesJoin5", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin5")
fieldmappings.addTable("CollegesBuffer")
collegefieldindex = fieldmappings.findFieldMapIndex("collegedist")
fieldmap = fieldmappings.getFieldMap(collegefieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(collegefieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin5", "CollegesBuffer", "ZonesJoin6", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin6")
fieldmappings.addTable("RetailCentersbuffer")
retailfieldindex = fieldmappings.findFieldMapIndex("RetailCentersdist")
fieldmap = fieldmappings.getFieldMap(retailfieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(retailfieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin6", "RetailCentersbuffer", "ZonesJoin7", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin7")
fieldmappings.addTable("BusStopsBuffer")
busfieldindex = fieldmappings.findFieldMapIndex("busdist")
fieldmap = fieldmappings.getFieldMap(busfieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(busfieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin7", "BusStopsBuffer", "ZonesJoin8", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin8")
fieldmappings.addTable("RailStationsbuffer")
railfieldindex = fieldmappings.findFieldMapIndex("RailStationsdist")
fieldmap = fieldmappings.getFieldMap(railfieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(railfieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin8", "RailStationsbuffer", "ZonesJoin9", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin9")
fieldmappings.addTable("Age_ACS_Tract")
agefieldindex = fieldmappings.findFieldMapIndex("B01001_calc_pctDependE")
fieldmap = fieldmappings.getFieldMap(agefieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(agefieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin9", "Age_ACS_Tract", "ZonesJoin10", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin10")
fieldmappings.addTable("Poverty_ACS_Tract")
povfieldindex = fieldmappings.findFieldMapIndex("B17020_calc_pctPovE")
fieldmap = fieldmappings.getFieldMap(povfieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(povfieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin10", "Poverty_ACS_Tract", "ZonesJoin11", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin11")
fieldmappings.addTable("Vehicles_ACS_Tract")
vehfieldindex = fieldmappings.findFieldMapIndex("B08201_calc_pctNoVehE")
fieldmap = fieldmappings.getFieldMap(vehfieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(vehfieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin11", "Vehicles_ACS_Tract", "ZonesJoin12", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin12")
fieldmappings.addTable("Roads")
roadsfieldindex = fieldmappings.findFieldMapIndex("BlockLength")
fieldmap = fieldmappings.getFieldMap(roadsfieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(roadsfieldindex, fieldmap)

arcpy.SpatialJoin_analysis("ZonesJoin12", "Roads", "ZonesJoin13", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")


fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable("ZonesJoin13")
fieldmappings.addTable("RoadsWithPathways")
bikefieldindex = fieldmappings.findFieldMapIndex("MeanBikeRating")
fieldmap = fieldmappings.getFieldMap(bikefieldindex)
fieldmap.mergeRule = "mean"
fieldmappings.replaceFieldMap(bikefieldindex, fieldmap)
pedfieldindex = fieldmappings.findFieldMapIndex("MeanPedRating")
fieldmap2 = fieldmappings.getFieldMap(pedfieldindex)
fieldmap2.mergeRule = "mean"
fieldmappings.replaceFieldMap(pedfieldindex, fieldmap2)

arcpy.SpatialJoin_analysis("ZonesJoin13", "RoadsWithPathways", "DemandScore", "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "INTERSECT")

print("Spatial Joins Complete!")


removefields = getFieldNames("DemandScore")
print(removefields)

arcpy.DeleteField_management("DemandScore", removefields)

# Clean up - delete intermediate feature classes
print("Deleting intermediate feature classes...")
removefcs = ["ZonesJoin1", "ZonesJoin2", "ZonesJoin3", "ZonesJoin4", "ZonesJoin5", "ZonesJoin6", "ZonesJoin7", "ZonesJoin8", "ZonesJoin9",
             "ZonesJoin10", "ZonesJoin11", "ZonesJoin12", "ZonesJoin13"]
for f in removefcs:
    arcpy.Delete_management(f)

print("Intermediate feature classes deleted!")


# Deal with null values in scores fields

joinfc = "DemandScore"
checkfields = ["PopDens2018", "JobDens2018", "lumixscore", "K12Schoolsdist", "ParksTrailheadsdist", "collegedist", "RetailCentersdist", "busdist", "RailStationsdist",
                "B01001_calc_pctDependE", "B17020_calc_pctPovE", "B08201_calc_pctNoVehE", "BlockLength", "MeanBikeRating", "MeanPedRating"]


with arcpy.da.UpdateCursor(joinfc, checkfields) as cursor:
    for row in cursor:
        if isinstance(row[0], (int, float, complex)) == False:
            row[0] = 0
        if isinstance(row[1], (int, float, complex)) == False:
            row[1] = 0
        if isinstance(row[2], (int, float, complex)) == False:
            row[2] = 0
        if isinstance(row[3], (int, float, complex)) == False:
            row[3] = 5000
        if isinstance(row[4], (int, float, complex)) == False:
            row[4] = 5000
        if isinstance(row[5], (int, float, complex)) == False:
            row[5] = 10
        if isinstance(row[6], (int, float, complex)) == False:
            row[6] = 5000
        if isinstance(row[7], (int, float, complex)) == False:
            row[7] = 5000
        if isinstance(row[8], (int, float, complex)) == False:
            row[8] = 5000
        if isinstance(row[9], (int, float, complex)) == False:
            row[9] = 0
        if isinstance(row[10], (int, float, complex)) == False:
            row[10] = 0
        if isinstance(row[11], (int, float, complex)) == False:
            row[11] = 0
        if isinstance(row[12], (int, float, complex)) == False:
            row[12] = 1000
        if isinstance(row[13], (int, float, complex)) == False:
            row[13] = 0
        if isinstance(row[14], (int, float, complex)) == False:
            row[14] = 0
        cursor.updateRow(row)
    del cursor, row


# Add fields for ratings
arcpy.AddField_management(joinfc, "popdensrating", "LONG")
arcpy.AddField_management(joinfc, "jobdensrating", "LONG")
arcpy.AddField_management(joinfc, "lumixrating", "LONG")
arcpy.AddField_management(joinfc, "schoolrating", "LONG")
arcpy.AddField_management(joinfc, "parkrating", "LONG")
arcpy.AddField_management(joinfc, "collegerating", "LONG")
arcpy.AddField_management(joinfc, "retailrating", "LONG")
arcpy.AddField_management(joinfc, "busrating", "LONG")
arcpy.AddField_management(joinfc, "railrating", "LONG")
arcpy.AddField_management(joinfc, "agerating", "LONG")
arcpy.AddField_management(joinfc, "povrating", "LONG")
arcpy.AddField_management(joinfc, "novehrating", "LONG")
arcpy.AddField_management(joinfc, "blocklengthrating", "LONG")
arcpy.AddField_management(joinfc, "BikeDemandScore", "DOUBLE")
arcpy.AddField_management(joinfc, "PedDemandScore", "DOUBLE")


# Calc each rating field
print('Calculating ratings fields...')
popfields = ["PopDens2018", "popdensrating"]
with arcpy.da.UpdateCursor(joinfc, popfields) as cursor:
    for row in cursor:
        if (row[0] <= 5):
            row[1] = 0
        elif (row[0] > 5 and row[0] <= 10):
            row[1] = 20
        elif (row[0] > 10 and row[0] <= 15):
            row[1] = 40
        elif (row[0] > 15 and row[0] <= 20):
            row[1] = 60
        elif (row[0] > 20 and row[0] <= 25):
            row[1] = 80
        elif (row[0] > 25):
            row[1] = 100
        cursor.updateRow(row)
    del cursor, row


jobfields = ["JobDens2018", "jobdensrating"]
with arcpy.da.UpdateCursor(joinfc, jobfields) as cursor:
    for row in cursor:
        if (row[0] <= 5):
            row[1] = 0
        elif (row[0] > 5 and row[0] <= 10):
            row[1] = 20
        elif (row[0] > 10 and row[0] <= 15):
            row[1] = 40
        elif (row[0] > 15 and row[0] <= 20):
            row[1] = 60
        elif (row[0] > 20 and row[0] <= 25):
            row[1] = 80
        elif (row[0] > 25):
            row[1] = 100
        cursor.updateRow(row)
    del cursor, row


lumixfields = ["lumixscore", "lumixrating"]
with arcpy.da.UpdateCursor(joinfc, lumixfields) as cursor:
    for row in cursor:
        if (row[0] <= 10):
            row[1] = 0
        elif (row[0] > 10 and row[0] <= 20):
            row[1] = 25
        elif (row[0] > 20 and row[0] <= 30):
            row[1] = 50
        elif (row[0] > 30 and row[0] <= 40):
            row[1] = 75
        elif (row[0] > 40):
            row[1] = 100
        cursor.updateRow(row)
    del cursor, row


schoolsfields = ["K12Schoolsdist", "schoolrating"]
with arcpy.da.UpdateCursor(joinfc, schoolsfields) as cursor:
    for row in cursor:
        if (row[0] <= 330):
            row[1] = 100
        elif (row[0] > 330 and row[0] <= 660):
            row[1] = 75
        elif (row[0] > 660 and row[0] <= 1320):
            row[1] = 50
        elif (row[0] > 1320 and row[0] <= 2640):
            row[1] = 25
        elif (row[0] > 2640):
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row


parksfields = ["ParksTrailheadsdist", "parkrating"]
with arcpy.da.UpdateCursor(joinfc, parksfields) as cursor:
    for row in cursor:
        if (row[0] <= 330):
            row[1] = 100
        elif (row[0] > 330 and row[0] <= 660):
            row[1] = 75
        elif (row[0] > 660 and row[0] <= 1320):
            row[1] = 50
        elif (row[0] > 1320 and row[0] <= 2640):
            row[1] = 25
        elif (row[0] > 2640):
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row


collegefields = ["collegedist", "collegerating"]
with arcpy.da.UpdateCursor(joinfc, collegefields) as cursor:
    for row in cursor:
        if (row[0] <= 1):
            row[1] = 100
        elif (row[0] > 1 and row[0] <= 2):
            row[1] = 50
        elif (row[0] > 2 and row[0] <= 4):
            row[1] = 25
        elif (row[0] > 4):
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row


retailfields = ["RetailCentersdist", "retailrating"]
with arcpy.da.UpdateCursor(joinfc, retailfields) as cursor:
    for row in cursor:
        if (row[0] <= 330):
            row[1] = 100
        elif (row[0] > 330 and row[0] <= 660):
            row[1] = 75
        elif (row[0] > 660 and row[0] <= 1320):
            row[1] = 50
        elif (row[0] > 1320 and row[0] <= 2640):
            row[1] = 25
        elif (row[0] > 2640):
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row


busfields = ["busdist", "busrating"]
with arcpy.da.UpdateCursor(joinfc, busfields) as cursor:
    for row in cursor:
        if (row[0] <= 330):
            row[1] = 100
        elif (row[0] > 330 and row[0] <= 660):
            row[1] = 75
        elif (row[0] > 660 and row[0] <= 1320):
            row[1] = 50
        elif (row[0] > 1320 and row[0] <= 2640):
            row[1] = 25
        elif (row[0] > 2640):
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row


railfields = ["RailStationsdist", "railrating"]
with arcpy.da.UpdateCursor(joinfc, railfields) as cursor:
    for row in cursor:
        if (row[0] <= 330):
            row[1] = 100
        elif (row[0] > 330 and row[0] <= 660):
            row[1] = 75
        elif (row[0] > 660 and row[0] <= 1320):
            row[1] = 50
        elif (row[0] > 1320 and row[0] <= 2640):
            row[1] = 25
        elif (row[0] > 2640):
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row


agefields = ["B01001_calc_pctDependE", "agerating"]
with arcpy.da.UpdateCursor(joinfc, agefields) as cursor:
    for row in cursor:
        if (row[0] <= 30):
            row[1] = 0
        elif (row[0] > 30 and row[0] <= 35):
            row[1] = 25
        elif (row[0] > 35 and row[0] <= 40):
            row[1] = 50
        elif (row[0] > 40 and row[0] <= 43):
            row[1] = 75
        elif (row[0] > 43):
            row[1] = 100
        cursor.updateRow(row)
    del cursor, row


povfields = ["B17020_calc_pctPovE", "povrating"]
with arcpy.da.UpdateCursor(joinfc, povfields) as cursor:
    for row in cursor:
        if (row[0] <= 3):
            row[1] = 0
        elif (row[0] > 3 and row[0] <= 6):
            row[1] = 20
        elif (row[0] > 6 and row[0] <= 9):
            row[1] = 40
        elif (row[0] > 9 and row[0] <= 12):
            row[1] = 60
        elif (row[0] > 12 and row[0] <= 15):
            row[1] = 80
        elif (row[0] > 15):
            row[1] = 100
        cursor.updateRow(row)
    del cursor, row


novehfields = ["B08201_calc_pctNoVehE", "novehrating"]
with arcpy.da.UpdateCursor(joinfc, novehfields) as cursor:
    for row in cursor:
        if (row[0] <= 3):
            row[1] = 0
        elif (row[0] > 3 and row[0] <= 6):
            row[1] = 20
        elif (row[0] > 6 and row[0] <= 9):
            row[1] = 40
        elif (row[0] > 9 and row[0] <= 12):
            row[1] = 60
        elif (row[0] > 12 and row[0] <= 15):
            row[1] = 80
        elif (row[0] > 15):
            row[1] = 100
        cursor.updateRow(row)
    del cursor, row


blockfields = ["BlockLength", "blocklengthrating"]
with arcpy.da.UpdateCursor(joinfc, blockfields) as cursor:
    for row in cursor:
        if (row[0] <= 300):
            row[1] = 100
        elif (row[0] > 300 and row[0] <= 400):
            row[1] = 75
        elif (row[0] > 400 and row[0] <= 500):
            row[1] = 50
        elif (row[0] > 500 and row[0] <= 900):
            row[1] = 25
        elif (row[0] > 900):
            row[1] = 0
        cursor.updateRow(row)
    del cursor, row


arcpy.management.CalculateField(joinfc, "BikeDemandScore", "((!popdensrating!*9)+(!jobdensrating!*11)+(!lumixrating!*10)+(!schoolrating!*10)+(!parkrating!*5)+(!collegerating!*10)+(!retailrating!*11)+(!busrating!*3)+(!railrating!*11)+(!agerating!*3)+(!novehrating!*4)+(!povrating!*6)+(!blocklengthrating!*2)+(!MeanBikeRating!*5))/100", "PYTHON3", '', "DOUBLE")
arcpy.management.CalculateField(joinfc, "PedDemandScore", "((!popdensrating!*9)+(!jobdensrating!*9)+(!lumixrating!*11)+(!schoolrating!*9)+(!parkrating!*5)+(!collegerating!*9)+(!retailrating!*12)+(!busrating!*4)+(!railrating!*10)+(!agerating!*3)+(!novehrating!*4)+(!povrating!*5)+(!blocklengthrating!*5)+(!MeanPedRating!*5))/100", "PYTHON3", '', "DOUBLE")

# Clean up - delete buffer feature classes
print("Deleting buffers...")
removebuffers = ["RailStationsbuffer", "K12Schoolsbuffer", "ParksTrailheadsbuffer", "RetailCentersbuffer", "CollegesBuffer", "BusStopsBuffer"]
for f in removebuffers:
    arcpy.Delete_management(f)

busstopsshp = os.path.join(temp_wd, "bus_stops.shp")
arcpy.Delete_management(busstopsshp)
busstopsbuffershp = os.path.join(temp_wd, "BusStopsBuffer.shp")
arcpy.Delete_management(busstopsbuffershp)

print("Buffers deleted!")

print('DONE!')