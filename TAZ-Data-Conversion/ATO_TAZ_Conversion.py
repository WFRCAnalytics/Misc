# -*- coding: utf-8 -*-
"""
Created on Mon Apr  6 13:21:57 2020

@author: jreynolds

Join ATO tables

"""



import pandas as pd
import geopandas as gp
import arcpy
import os
import shutil
from pathlib import Path
import glob
import time

# output directory
output_directory = r'E:/'

# directory of input tables
in_tables = r"E:\Projects\Misc\TAZ-Data-Conversion\ATO_RTP_Data_Revised"
in_tables = r"E:\Projects\Misc\TAZ-Data-Conversion\ATO_RTP_Data"

#================
# FUNCTIONS
#================

# returns colnames of a pandas dataframe and their index like R does when you call colnames
def colnames(dataframe):
    values = (list(enumerate(list(dataframe.columns.values), 0)))
    for value in values:
        print(value)

#================
# MAIN
#================

# directory where processed outputs will go
results = os.path.join(output_directory, 'Conversion_Results_{}'.format(time.strftime('%Y%m%d_%H%M%S',time.localtime())))

# create outputs directory 
Path(results).mkdir(parents=True, exist_ok=True)

# read in base table
base_table = pd.read_csv("E:\Projects\Misc\TAZ-Data-Conversion\Datasets\ATO_TAZ_Base_Table.csv").sort_values(by=['TAZID'])

# get list of tables
dbfs = glob.glob(os.path.join(in_tables,'*.dbf'))

# convert dbfs to csvs for pandas
for dbf in dbfs:
    
    # get some metadata
    filename = os.path.basename(dbf)
    print('working on {}...'.format(filename))
    year = os.path.basename(dbf)[22:26]
    
    # convert to csv and read into pandas
    csv = filename.replace('dbf', 'csv')
    arcpy.TableToTable_conversion(dbf, results, csv)
    temp_table = pd.read_csv(os.path.join(results, csv))
    
    # subset to relevant columns
    temp_table = temp_table[['TAZID', 'HH', 'JOB', 'AUTO_JB', 'TRAN_JB', 'AUTO_HH', 'TRAN_HH', 'COMP_AUTO', 'COMP_TRAN']]
    
    # format field names (REARRANGE NAMING)
    new_field_names = ['TAZID', 'HH_{}', 'JOB_{}', 'AUTO_JB_{}', 'TRAN_JB_{}', 'AUTO_HH_{}', 'TRAN_HH_{}', 'AUTO_CP_{}', 'TRAN_CP_{}']
    new_field_names = [name.format(year[-2:]) for name in new_field_names]
    temp_table.columns = new_field_names
    
    # merge table on TAZ ID
    base_table = base_table.merge(temp_table, left_on = 'TAZID', right_on = 'TAZID' , how = 'inner')
    
    # delete remnants
    try: os.remove(os.path.join(results, csv))
    except: pass

    try: os.remove(os.path.join(results, csv + '.xml'))
    except: pass
    
    try: shutil.rmtree(os.path.join(results, 'info'))
    except: pass

    
# export final table
base_table.to_csv(os.path.join(results, 'Access_to_Opportunity_WorkRelated_TAZ_Based.csv'),index=False)


# (bonus) join back to TAZ geometry via geopandas
taz_geometry = gp.read_file(r"E:\Access_To_Opportunities\TAZ-Data-Conversion\TAZ_geometry.shp")
ato_output = taz_geometry.merge(base_table, on='TAZID')
ato_output.to_file(os.path.join(results,"Access_to_Opportunity_WorkRelated_TAZ_Based.shp"))






