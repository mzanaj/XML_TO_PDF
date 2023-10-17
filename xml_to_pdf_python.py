import xml.etree.ElementTree as ET
import Versaterm_Connect
import psycopg2
import traceback
import pandas as pd
import os
from zipfile import ZipFile 
import shutil
import re
import random
import string
from fpdf import FPDF
import json

#GET field ucr_ext from Table ucr_ext from Versaterm
def sensitive_case(case_id):
    #print('Connecting to PostgreSQL database....')
    cnxn= None
    
    try: 
        # read connection parameters
        params = Versaterm_Connect.config_w_encryption()
        
        #Connection to DB
        cnxn = psycopg2.connect(**params)
    
        #print('Connection to PostgreSQL database SUCCESSFUL')

        #Cursor Object
        cursor = cnxn.cursor()
    
        query_text = "select concat (LTRIM(RTRIM( cast ( go_data.rucr as text ))) , LTRIM(RTRIM( cast ( go_data.rext as text ))) ) as rucr_ext FROM go_data WHERE go_data.primary_key= (%s)"
        
        #Testing query 
        cursor.execute(query_text, (case_id,))
        
        try:
            
            #Retrieve the records from the database
            records = cursor.fetchall()[0][0]

            sensitive_codes= ['9090', '54011', '549933', '549934', '54991'] 
            if(records in sensitive_codes):
                return True
            else:
                return False
        except:
            #print("Something wrong with case_id", case_id)
            return -1
    #Bad Credentials Exception
    except Exception as err:
        print(f"Connection to PostgreSQL FAILED! {err=}, {type(err)=}")
        
        #Where the exception happened
        print(traceback.format_exc())  # or: traceback.print_exc()
        raise
        
    #Close Connection
    finally:
        if cnxn is not None:
            #Close Session
            cursor.close()
            cnxn.close()
            #print('Connection to PostgreSQL database CLOSED')

#The heart of the program, it will transverse the xml and put the relevant data inside the pdf in accordance to our aesthetics specs.
#The idea is that you start with root, and loop over its children --> at this point if the children have children of themselves you call
#in a helper function (this allows for a recursive function that goes down all sub_levels, where even if the children of the children of the children ...
# have children, that data will be transversed given the recursrive nature of the function where it calls itself if the current element has sub_elements).

def xml_to_pdf(file_path, pdf, off_name):

    first_id=1
    
    #Get DATA
    data=file_path

    #Build Tree
    tree = ET.parse(data)

    #Get Root
    root = tree.getroot()

    #Get Children of root
    children_root= list(root)
    
    veich_numb=1

    
    text_dict = {'ActivityDescriptionText': '', 'ActivityDescriptionTextHtml': '', 'BinaryObject.Base64':''}

    def get_age(temp_parent):
        try:
            #Create a more robust method (look all children, with tag person age, and use that to calculate age-- no hard coding)
            age = int(temp_parent.find('{http://crash.dps.utah.gov/jxdm/1.0/extension}PersonAge').text)
            return age
        except:
            return -1
    #Changes text size based if on tag (can be expanded to accomodate more headings)
    def heading(text):
        if(text in ["IncidentResponse","IncidentLocation","InvolvedVehicleOperator", "InvolvedVehiclePassenger", "InvolvedVehicle","IncidentEvent" ]):
            pdf.set_font('Times', 'B', 13)
        else:
            pdf.set_font('Times')
            pdf.set_font_size(11.0)
    
    #Recursive helper function
    def helper_function(temp_parent, temp_children, n):

        x=0

        for sub_child in temp_children:
            field= temp_parent.find(sub_child.tag)
            field_a = field.attrib if len(field.attrib) !=0 else ""
            
            if(sub_child.tag.split('}')[1] =="ID" and temp_parent.tag.split('}')[1]=="ActivityID"):
                global id_case
                id_case=sub_child.text
            
            indentation= "    "*n
            #Write to pdf  
            if(sub_child.tag.split('}')[1] == 'BinaryObject.Base64'):
                text_dict['BinaryObject.Base64'] = sub_child.text
                return
            #Fields that we don't put in PDF
            elif(sub_child.tag.split('}')[1] == 'pin' or sub_child.tag.split('}')[1] == 'activitydescriptionid'):
                continue
            #Filter out details of MINOR PASSENGERS
            elif(temp_parent.tag.split('}')[1]=='InvolvedVehiclePassenger' and get_age(temp_parent)>=0 and get_age(temp_parent)<18):
                try:
                    pass_attribs= temp_children
                    sensitive_info = ['PersonName', 'Residence', 'PersonBirthDate','PersonPhysicalDetails','formname', 'PersonAge', 'pin']
                    for x in pass_attribs:
                            if(x.tag.split('}')[1] not in sensitive_info):
                                field= temp_parent.find(x.tag)
                                field_a = field.attrib if len(field.attrib) !=0 else ""
                                if(type(field_a)==dict):      
                                        pdf.cell(10, 5,indentation+x.tag.split('}')[1], 0, 0)

                                        if(len(field_a['Description']) >100):
                                            pdf.ln(1)
                                            pdf.multi_cell(0, 5,field_a['Description'] , align='L', border = 0,fill= False)
                                        else:
                                            pdf.cell(210, 5,indentation+field_a['Description'], 0 , 1 ,align='C')
                                else:
                                    helper_function(x, list(x), n+1)
                            else:
                                if(x.tag.split('}')[1] not in ['formname', 'pin']):
                                    pdf.cell(10, 5,indentation+x.tag.split('}')[1], 0, 1)
                    return 
                    
                except:
                    print("Something wrong with person age parameter")
                    pass

            #No special heading (print if not empty)
            else:
               
                try:
                    if(sub_child.text != None):
                        if(sub_child.text !="" and not sub_child.text.isspace()):
                            heading(sub_child.text)
                            pdf.cell(10, 5,indentation+sub_child.tag.split('}')[1], 0, 0)
                except:
                    print("Problem with None Type  ", sub_child.tag.split('}')[1], sub_child.text)
                    pass
            #Text is inside description if type dict
            if(type(field_a)==dict):
                heading(field_a['Description'])
                #If field is too big, just use multicell which create a new line and allows for things not too be jammed in one line
                if(len(field_a['Description']) >100):
                    pdf.ln(1)
                    pdf.multi_cell(0, 5,field_a['Description'] , align='L', border = 0,fill= False)
                else:
                    #pdf.multi_cell(160, 10,field_a['Description'] , align='R', border = 0,fill= False)
                    pdf.cell(210, 5,indentation+field_a['Description'], 0 , 1 ,align='C')
            
            #Text in inside .text
            else:

                try:
                    if(field.text!=None):
                        heading(field.text)
                        if(len(field.text) >100):
                            pdf.ln(5)
                            pdf.multi_cell(0, 5,field.text , align='L', border = 0,fill= False)


                        else:
                            if(field.text!="" and not field.text.isspace()):                        
                                pdf.cell(210, 5,indentation+str(field.text)+" "+str(field_a), 0 , 1 ,align='C')

                except Exception:
                    print("Problem field_text", field)
                    pass

            #Recursion, if there are kids re-call self
            if(len(list(sub_child))>0): 
                #Have some kind of recursion/ exhaustive loop (current system it just mere brute force :(  
                helper_function(sub_child, list(sub_child), n+1)

            x+=1
            
        return 

    #Get each element, associate with each child of root (i.e. reminder of tree)
    for child in children_root:

        pdf.set_font('Times', 'B', 13)
        # pdf.cell(30, 10,"SECTION: ", 0, 0)
        pdf.cell(30,10,child.tag.split('}')[1], 0, 1)
    
        temp_parent= child
        temp_children= list(child)

        x=0

        #No sub_element associated with current section (usually, submission status) 
        if(len(temp_children)==0):
            field_ab = temp_parent.attrib if len(temp_parent.attrib) !=0 else ""
            pdf.set_font('Times')
            pdf.set_font_size(11.0)

            #Don't print if empty
            if(temp_parent.text !="" and not temp_parent.text.isspace()):
                pdf.cell(10, 5,"    "+temp_parent.tag.split('}')[1], 0, 0)
                pdf.cell(200, 5,temp_parent.text, 0,0, align ='C')
                pdf.cell(90, 5,field_ab, 0,1)

        #Loop over each element of the temp_parent
        for sub_child in temp_children:
            heading(sub_child.tag.split('}')[1])

            try:
                if(sub_child.text!=None):

                    field = child.find(sub_child.tag)
                    field_a = field.attrib if len(field.attrib) !=0 else ""
                   
                    if((sub_child.text!="" and not sub_child.text.isspace()) or len(list(sub_child))>0):
                        pdf.set_text_color(r=0, g=0, b=0)    
                        if(sub_child.tag.split('}')[1] == 'ActivityDescriptionText'):
                            text_dict['ActivityDescriptionText'] = sub_child.text
                        elif(sub_child.tag.split('}')[1] == 'ActivityDescriptionTextHtml'):
                            text_dict['ActivityDescriptionTextHtml'] = sub_child.text
                        elif(sub_child.tag.split('}')[1] == 'pin' or sub_child.tag.split('}')[1] == 'activitydescriptionid'):
                            continue
                        else:
                            if(len(list(sub_child))>0):
                                
                                if(sub_child.tag.split('}')[1] in ["InvolvedVehicleOperator", "InvolvedVehiclePassenger", "InvolvedVehicle","IncidentEvent" ]):
                                    pdf.cell(10, 5,str(sub_child.tag.split('}')[1])+" UNIT # "+str(veich_numb), 0, 1)
                                    
                                else:
                                    pdf.cell(10, 5,sub_child.tag.split('}')[1], 0, 1)
                            else:
                                if(sub_child.tag.split('}')[1]in ["InvolvedVehicleOperator", "InvolvedVehiclePassenger", "InvolvedVehicle","IncidentEvent" ]):
                                    pdf.cell(10, 5,str(sub_child.tag.split('}')[1])+" UNIT # "+str(veich_numb), 0, 0)

                                else:
                                    pdf.cell(10, 5,sub_child.tag.split('}')[1], 0, 0)
                                   

            except:
                print("Problem in sub_child")
                pass

            pdf.set_font('Times')
            pdf.set_font_size(11.0)

            if(type(field_a)==dict):
                        
                if(len(field_a['Description']) >100):
                    pdf.ln(1)
                    
                    pdf.multi_cell(0, 5,field_a['Description'] , align='L', border = 0,fill= False)
                else:
                    pdf.cell(210, 5,field_a['Description'], 0 , 1 ,align='C')

            else:
                try:
                    
                    if(field.text!=None):
                                                         
                        if(len(field.text) >100):

                            if(sub_child.tag.split('}')[1] != 'ActivityDescriptionText' and 
                               sub_child.tag.split('}')[1] != 'ActivityDescriptionTextHtml'):
                                pdf.ln(5)
                                pdf.multi_cell(0, 5,field.text , align='L', border = 0,fill= False)
                        else:
                            if(field.text!="" and not field.text.isspace()):
                                pdf.cell(210, 5,str(field.text)+" "+str(field_a) , 0 , 1 ,align='C')

                except Exception:
                    print("Problem in field.text") 
                    pass

            #Sub_sub_elements
            if(len(list(sub_child))>0): 
                #Recursion (each element and their respective sub_element will be reached)
                helper_function(sub_child, list(sub_child), 1)

            x+=1
        if(child.tag.split('}')[1]=='InvolvedVehicleEvent'):
            veich_numb+=1

        pdf.ln(5)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x()+185,pdf.get_y())
        pdf.ln(5)

    
    #Remove extra space/lines from Officer Text Description 
    def remove_empty_lines(text):
        
        lines = text.split('\n')
        non_empty_lines = [line for line in lines if line.strip() != '']
        return '\n'.join(non_empty_lines)
    
    #Accident Diagram
    if(text_dict['BinaryObject.Base64']!=""):
        import base64
        data = text_dict['BinaryObject.Base64']
        imgdata = base64.b64decode(data)
        filename = '/xml_to_pdf/traffic_image.jpeg'  # I assume you have a way of picking unique filenames

        with open(filename, 'wb') as f:
                f.write(imgdata)

        pdf.add_page()
        pdf.set_font('Times', 'B', 13)     
        pdf.image('/xml_to_pdf/traffic_image.jpeg',  5, 10, 200)
        pdf.cell(30, 10, 'Accident Diagram', 0, 0, 'C')

    #Narrative Text
    if(text_dict['ActivityDescriptionText'] !=""):
        #####REMOVE EXTRA LINES FROM DESCRIPTION (CODE BELOW-- INSERT HERE)
        pdf.add_page()
        pdf.set_font('Times', 'B', 13)     
        pdf.cell(30, 10, 'Narrative Text', 0, 1, 'C')
        pdf.set_font('Times')  
        pdf.set_font_size(11.0)
        pdf.multi_cell(0, 10,remove_empty_lines(text_dict['ActivityDescriptionText']) , align='L')
    

    f_name='{off_name}.pdf'.format(off_name = off_name)
    file_loc= os.path.join(r'\AccidentPDF', f_name)
    #file_loc= os.path.join(r'\temp', f_name)

    pdf.output(file_loc, 'F')
    pdf.close()

def xml_to_txt(root):
    f=open("/xml_to_pdf/xml_to_txt.txt", 'w')       
    #Recursive helper function
    def helper_function(temp_parent, temp_children, n):

        x=0
        indentation= "       "*n

        for sub_child in temp_children:
            field= temp_parent.find(sub_child.tag)
            field_a = field.attrib if len(field.attrib) !=0 else ""
            if(sub_child.tag.split('}')[1] !='BinaryObject.Base64'):
                if(field_a!= type(None)):
                    result = json.dumps(field_a)
                    temp_output=indentation+sub_child.tag.split('}')[1]+ "\t "+str(field.text)+"\t"+result+"\n"
                else:
                    temp_output=indentation+sub_child.tag.split('}')[1]+"\t"+str(field.text)+"\n"
                
                f.write(str(temp_output))   
        
            if(len(list(sub_child))>0): 
                #Have some kind of recursion/ exhaustive loop (current system it just mere brute force :(  
                helper_function(sub_child, list(sub_child), n+1)
        
            x+=1
        
        return 

     #Get each element, associate with each child of root (i.e. reminder of tree)
    for child in list(root):
        temp_output="SECTION: "+child.tag.split('}')[1]+"\n"
        f.write(str(temp_output))

        temp_parent= root.findall(child.tag)[0]
        temp_children= list(child)

        x=0

        #No sub_element associated with current section (usually, submission status) 
        if(len(temp_children)==0):
            field_ab = temp_parent.attrib if len(temp_parent.attrib) !=0 else ""
            if(field_ab!= type(None)):
                result = json.dumps(field_ab)
                temp_output="     "+temp_parent.tag.split('}')[1]+ "\t"+str(temp_parent.text)+"\t"+result+"\n"
            else:
                temp_output="     "+temp_parent.tag.split('}')[1]+"\t"+str(temp_parent.text)+"\n"
            f.write(str(temp_output))   

        #Loop over each element of the temp_parent
        for sub_child in temp_children:
            f.write("\n")
            field= temp_parent.find(sub_child.tag)
            field_a = field.attrib if len(field.attrib) !=0 else ""
            if(sub_child.tag.split('}')[1]!='ActivityDescriptionTextHtml'):
                if(field_a!=type(None)):
                    result = json.dumps(field_a)
                    temp_output="     "+sub_child.tag.split('}')[1]+"\t"+str(field.text)+"\t"+result+"\n"       
                else:
                    temp_output="     "+sub_child.tag.split('}')[1]+"\t"+str(field.text)+"\t"+"\n"          
                f.write(str(temp_output))

            #Sub_sub_elements
            if(len(list(sub_child))>0): 
                #Have some kind of recursion/ exhaustive loop (current system it just mere brute force :( 
                helper_function(sub_child, list(sub_child), 1)

            x+=1

        f.write("<--------------------------------------------------------------------------------------------------------------------------------------------------------------->\n")

    f.close()

#https://realpython.com/python-send-email/
def email(filename):
    
    import email, smtplib, ssl
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    subject = "TESTING - XML AUDIT ALERT SYSTEM"
    body = 'Hello Fellow Recorders (?), \n\nThis is alert being generated from the XML_to_PDF production script signifing a potential update/change/error. \n\nPlease, take a look at the attached .txt file for a more detailed explanation. \n\nBest, \nPython'
    sender_email = "sender@hotmail.com"
    receiver_email = ['receveiver@hotmail.com',]
    cc_email = ['cc@hotmail.com',]
    
    # Create a multipart message and set headers
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = ", ".join(receiver_email)
    message["Subject"] = subject
    message["Cc"] = ", ".join(cc_email)

    # Add body to email
    message.attach(MIMEText(body, "plain"))
    
    #Add attachement 
    
    # Open PDF file in binary mode
    with open(filename, "rb") as attachment:
        # Add file as application/octet-stream
        # Email client can usually download this automatically as attachment
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())

    # Encode file in ASCII characters to send by email    
    encoders.encode_base64(part)

    # Add header as key/value pair to attachment part
    part.add_header(
        "Content-Disposition",
        f"attachment; filename= {filename}",
    )

    # Add attachment to message and convert message to string
    message.attach(part)
    
    text = message.as_string()

    # Log in to server using secure context and send email
    with smtplib.SMTP("webmail.slcgov.com") as server:
        server.sendmail(sender_email, receiver_email, text)
        print("Email Sent")
    #delete txt file 
    os.remove(filename)

#Given we save pdfs with their ID number and year, and that sometimes xmls are updated and as a result a new xml will be generated, how do we handle this case
#when the same record has the same case_id?
#Solution is to keep a list of all case id that we convert to pdf, if we've already encountered the current case_id just rename the new one case_id_A, B, C ....
#Up to Z (meaning the same record has been updated 26 times -- highly unlikely (16 was the maximum from historical data), yet even at this point if for some
#reason the same case id is updated 27 times the new name will be case_id_xxxxxxxxxx where x represent a random code. 
#This mechanism allows to keep track each version of the same XMl. 
def case_id_name_check(case_id):
    df = pd.read_csv("/xml_to_pdf/case_id_list.csv") 
    if case_id in df['case_id'].values:
        return True
    else:
        #Add to Dataset
        df.loc[len(df)] = case_id
        df.to_csv("/xml_to_pdf/case_id_list.csv", index=False)
        return False

def official_name(case_id):
    #Loop until FALSE is received from case_id_n_c (i.e. no match for current name)
    while(True):
        alphabet= ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'] 
        if(case_id_name_check(case_id)==True):
            for x in alphabet:
                if(case_id_name_check("{case_id}_{x}".format(case_id= case_id, x=x))==False):
                    return "{case_id}_{x}".format(case_id= case_id, x=x)
                elif(case_id_name_check("{case_id}_{x}".format(case_id= case_id, x=x))==True and x=='Z'):
                    code=''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(10))
                    case_id_name_check("{case_id}_{code}".format(case_id= case_id, code=code))
                    return "{case_id}_{code}".format(case_id= case_id, code=code)
        else:
            return case_id
        
def unzip():
    directory = '/AccidentXML'
    #UNZIP XML DIRECOTORIES, save files, and move original zip to processedAccidentXML
    for subdir, dirs, files in os.walk(directory):
        for file in files:
            f=os.path.join(subdir, file)
            raw_path=r'%s' % f

            #Check if zipped of normal 
            split_tup = os.path.splitext(raw_path)

            if(split_tup[1] == ".zip"):
                #Unzip
                with ZipFile(raw_path, 'r') as zObject:
                    # Extracting specific file in the zip into a specific location. 
                    zObject.extractall(directory)
                    zObject.close()

                f2=os.path.join("/ProccessedAccidentXML", file)
                raw_path2=r'%s' % f2
                shutil.move(raw_path,raw_path2 )

def xml_files():
    txt_num = 2
    #Convert XMLS into PDFS and save to AccidentPDF
    directory = '/AccidentXML'
    
    for subdir, dirs, files in os.walk(directory):
        for file in files:
            f=os.path.join(subdir, file)
            raw_path=r'%s' % f

             #Check if XML 
            split_tup = os.path.splitext(raw_path)

            if(split_tup[1] == ".xml"):
                tree = ET.parse(raw_path)

                #Get Root
                root = tree.getroot()
                
                try:
                    #Case_ID
                    case_id=root.find('{http://crash.dps.utah.gov/jxdm/1.0/extension}CrashDrivingIncident').find('{http://www.it.ojp.gov/jxdm/3.0.3/crash}ActivityID').find('{http://www.it.ojp.gov/jxdm/3.0.3/crash}ID').text
                    jurisdiction= case_id[0:2]
                
                    # #Date
                    # date=root.find('{http://crash.dps.utah.gov/jxdm/1.0/extension}CrashDrivingIncident').find('{http://www.it.ojp.gov/jxdm/3.0.3/crash}ActivityDateTime').text
                    # from datetime import datetime
                    # date= date[0:10]
                    # date_format = '%Y-%m-%d'
                    # date_obj = datetime.strptime(date, date_format)
                    # val_date= datetime.strptime("2023-09-01", date_format)
                    
                    #Only cases since September
                    if(jurisdiction =="SL"):
                        clean_case_id = re.sub('[^A-Za-z0-9]+', '', case_id)
                        FLAG=sensitive_case(clean_case_id)

                        #Connection to POSTGRES
                        if(FLAG==False):
                            #Output
                            off_name= official_name(clean_case_id)

                            #Continue 
                            print('\033[92m'+"NON-SENSITIVE CASE",case_id, raw_path+'\033[0m')

                            #PDF CLASS
                            class PDF(FPDF):
                                # Page footer
                                def footer(self):
                                    #Position at 1.5 cm from bottom
                                    self.set_y(-15)
                                    # Arial italic 8
                                    self.set_font('Arial', 'I', 9)
                                    # Page number
                                    self.cell(0, 10, off_name + " "+'Page ' + str(self.page_no()) + '/{nb}', 0, 0, 'C')

                            #Instantiation of inherited class
                            pdf = PDF()
                            pdf.alias_nb_pages()
                            pdf.add_page()

                            #Header
                            pdf.image('/logo_pb.png', 10, 8, 33)
                            pdf.set_font('Times', 'BIU', 17)
                            pdf.cell(80)

                            # Calculate width of title and position
                            w = pdf.get_string_width('Utah EMVA Report') + 6
                            pdf.set_x((210 - w) / 2)

                            # Title
                            pdf.cell(w, 10, 'Utah EMVA Report', 0, 0, 'C')

                            # Line break
                            pdf.ln(30)
                            xml_to_pdf(raw_path,pdf,off_name)

                            #Delete picture that is created after saving it in pdf
                            if os.path.isfile("/traffic_image.jpeg"):
                                os.remove("/traffic_image.jpeg")

                        elif(FLAG==True):
                            print('\033[93m'+ "SENSITIVE CASE",case_id, raw_path + '\033[0m')

                        else:
                            print('\033[91m' +"BAD CASE ID",case_id, raw_path +'\033[0m')
                            #Create txt file for RECORDS
                            xml_to_txt(root)
                            #Email such txt file
                            email('/xml_to_pdf/xml_to_txt.txt')

                    else:
                        print('\033[94m' +"DIFFERENT JURISDICTION", case_id +'\033[0m')
                except Exception as e:
                    print('\033[91m' +"NO CASE ID", raw_path +'\033[0m')
                    xml_to_txt(root)
                    email("/xml_to_pdf/xml_to_txt.txt")
                    #raise
                    pass
def delete_xmls():
    directory = '/AccidentXML'
    #UNZIP XML DIRECOTORIES, save files, and move original zip to processedAccidentXML
    for subdir, dirs, files in os.walk(directory):
        for file in files:
            f=os.path.join(subdir, file)
            raw_path=r'%s' % f
            os.remove(raw_path)

if __name__=='__main__':
    unzip()
    xml_files()
    delete_xmls()
