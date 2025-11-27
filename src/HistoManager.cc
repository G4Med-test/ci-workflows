#include "HistoManager.hh"
#include "HistoManagerHelper.hh"
#include <sstream>
#include <array>
#include <string>

using HistoPropertiesType = std::array<float, 3>;

std::string my_to_string(const double dbl)
{
  std::ostringstream strs;
  strs << dbl;
  std::string str = strs.str();
  return str;
}


HistoManager::HistoManager()  :
  fOn(false)//,
  // fFileName("out.root")
{
  // G4cout<<"HistoManager::HistoManager()"<<G4endl;
  // fMessenger = new HistoManagerMessenger(this);

}

HistoManager::~HistoManager() 
{
  // if(fMessenger)
  //   delete fMessenger;
}

void HistoManager::Book() 
{
  G4AnalysisManager* analysisManager = G4AnalysisManager::Instance();
  // analysisManager->SetNtupleMerging(true);
  analysisManager->SetVerboseLevel(1);
  analysisManager->SetDefaultFileType("xml");

  G4String fileName = HistoManagerHelper::Instance()->GetOutFileName();
  
  // G4cout<<"Opening outputfile: "<<fileName<<G4endl;
  G4bool fileOpen = analysisManager->OpenFile(fileName);
  if (!fileOpen) {
    G4cout << "\n---> HistoManager::Book(): cannot open " 
           << fileName 
           << G4endl;
    return;
  }

  std::vector<double> angs;  
  std::vector<double> accept;

  std::map<std::string, HistoPropertiesType> HistoProperites{
  {"hH1_11.4",{  18, 0, 180}},
  {"hH1_14.4",{  18, 0, 180}},
  {"hH1_17.2",{  16, 0, 160}},		
  {"hH1_19.4",{  15, 0, 150}},		
  {"hH2_11.4",{  19, 7, 140}},		
  {"hH2_14.4",{  18, 7, 133}},		
  {"hH2_17.2",{  18, 0, 126}},		
  {"hH2_19.4",{  18, 0, 126}},		
  {"hH3_11.4",{  18, 0, 126.667}},	
  {"hH3_14.4",{  17, 0, 113.333}},	
  {"hH3_17.2",{  15, 0, 100}},		
  {"hH3_19.4",{  13, 0, 93.3333}},	
  {"hHe4_2.2",{  19, 5, 100}},		
  {"hHe4_4.9",{  19, 5, 100}},		
  {"hHe4_7.6",{  19, 5, 100}},		
  {"hHe4_14.4",{ 19, 5, 100}},		
  {"hHe4_18",{   19, 5, 100}},		
  {"hHe4_21.8",{ 19, 5, 100}},		
  {"hLi6_2.2",{  18, 5, 95}},		
  {"hLi6_4.9",{  18, 5, 95}},		
  {"hLi6_7.6",{  18, 5, 95}},		
  {"hLi6_14.4",{ 18, 5, 95}},		
  {"hLi6_18",{   17, 5, 90}},		
  {"hLi6_21.8",{ 14, 5, 75}},		
  {"hLi7_2.2",{  17, 9.14286, 86.8571}},
  {"hLi7_4.9",{  17, 9.14286, 86.8571}},
  {"hLi7_7.6",{  17, 9.14286, 86.8571}},
  {"hLi7_14.4",{ 17, 9.14286, 86.8571}},
  {"hLi7_18",{   15, 9.14286, 77.7143}},	
  {"hLi7_21.8",{ 13, 9.14286, 68.5714}},
  {"hBe7_2.2",{  18, 9.14286, 91.4286}},
  {"hBe7_4.9",{  17, 9.14286, 86.8571}},
  {"hBe7_7.6",{  16, 9.14286, 82.2857}},
  {"hBe7_14.4",{ 16, 9.14286, 82.2857}},
  {"hBe7_18",{   16, 9.14286, 82.2857}},	
  {"hBe7_21.8",{ 13, 9.14286, 68.5714}},
  {"hBe9_2.2",{  17, 8, 76}},		
  {"hBe9_3.5",{  17, 8, 76}},		
  {"hBe9_4.9",{  17, 8, 76}},		
  {"hBe9_7.6",{  17, 8, 76}},		
  {"hBe9_11.1",{ 17, 8, 76}},		
  {"hBe9_14.4",{ 17, 8, 76}},		
  {"hB10_2.2",{  17, 8, 76}},		
  {"hB10_3.5",{  17, 8, 76}},		
  {"hB10_4.9",{  17, 8, 76}},		
  {"hB10_7.6",{  17, 8, 76}},		
  {"hB10_11.1",{ 17, 8, 76}},		
  {"hB10_14.4",{ 16, 8, 72}},		
  {"hB11_2.2",{  16, 11.4545, 72.5455}},
  {"hB11_3.5",{  17, 7.63636, 72.5455}},
  {"hB11_4.9",{  17, 7.63636, 72.5455}},
  {"hB11_7.6",{  17, 7.63636, 72.5455}},
  {"hB11_11.1",{ 17, 7.63636, 72.5455}},
  {"hB11_14.4",{ 15, 7.63636, 68.7273}} };

  for(size_t i=0; i<As.size(); i++)
    {
      std::string isotopename="";
      if(Zs[i]==1)
	isotopename="H";
      else if(Zs[i]==2)
	isotopename="He";
      else if(Zs[i]==3)
	isotopename="Li";
      else if(Zs[i]==4)
	isotopename="Be";  
      else if(Zs[i]==5)
	isotopename="B";
      std::string isotopename2 = isotopename;
      isotopename+=my_to_string(As[i]);
      //   Be9                        B
      if( (Zs[i]==4 && As[i]==9) || (Zs[i]==5) )
  	{
  	  angs.clear();
  	  accept.clear();
  	  angs   = {2.2, 3.5, 4.9, 7.6, 11.1, 14.4};
  	  accept = {0.4, 0.4, 0.4, 1.5,  1.5,  1.5};
  	}
      else if( Zs[i]==1 )
  	{
  	  angs.clear();
  	  accept.clear();
  	  angs   = {11.4, 14.4, 17.2, 19.4};
  	  accept = {1.5,   1.5,  1.5,  1.5};
  	}
      else
  	{
  	  angs.clear();
  	  accept.clear();
  	  angs   = {2.2, 4.9, 7.6, 14.4,  18, 21.8};
  	  accept = {0.4, 0.4, 1.5,  1.5, 1.5,  1.5};
  	}
      for(const auto& ang : angs)
  	{
	  std::string hname = "h"+isotopename+"_"+my_to_string(ang);
	  HistoPropertiesType thisHistoProperties = HistoProperites.at(hname);
	  int thisId = analysisManager->CreateH1(hname, hname,
						 thisHistoProperties[0],
						 thisHistoProperties[1],
						 thisHistoProperties[2]);
	  // G4cout<<"Creating histogram "<<hname<<" with id: "<<thisId
	  // 	<<" n bin: "<< thisHistoProperties[0]
	  // 	<<" x min: "<< thisHistoProperties[1]
	  // 	<<" x max: "<< thisHistoProperties[2]	    	    
	  // 	<<G4endl;
	  HistoIds.insert(std::make_pair(hname,thisId));
	}//end loop on angles
  
    }//end loop on isotopes
  
  fOn = true;
  
  // G4cout << "\n----> Output file is open in " 
  //        << analysisManager->GetFileName() << "." 
  //        << analysisManager->GetFileType() << G4endl;
}


void HistoManager::FillSecondaries(const G4int A, const G4int Z, const G4double Ek, const G4double theta)
{
  
  std::vector<double> angs;  
  std::vector<double> accept;

  std::string isotopename="";
  if(Z==1)
    isotopename="H";
  else if(Z==2)
    isotopename="He";
  else if(Z==3)
    isotopename="Li";
  else if(Z==4)
    isotopename="Be";  
  else if(Z==5)
    isotopename="B";
  else
    return;
  std::string isotopename2 = isotopename;
  isotopename+=my_to_string(A);
  //   Be9                        B
  if( (Z==4 && A==9) || (Z==5) )
    {
      angs.clear();
      accept.clear();
      angs   = {2.2, 3.5, 4.9, 7.6, 11.1, 14.4};
      accept = {0.4, 0.4, 0.4, 1.5,  1.5,  1.5};
    }
  else if( Z==1 )
    {
      angs.clear();
      accept.clear();
      angs   = {11.4, 14.4, 17.2, 19.4};
      accept = {1.5,   1.5,  1.5,  1.5};
    }
  else
    {
      angs.clear();
      accept.clear();
      angs   = {2.2, 4.9, 7.6, 14.4,  18, 21.8};
      accept = {0.4, 0.4, 1.5,  1.5, 1.5,  1.5};
    }
  for(size_t j=0; j<angs.size(); j++)	
    {
      if( (theta >= (angs[j]-accept[j])) && (theta <= (angs[j]+accept[j])) )
	{
	  std::string hname = "h"+isotopename+"_"+my_to_string(angs[j]);
	  // G4cout<<"Trying to fill"<<hname<<G4endl;
	  if(HistoIds.find(hname) != HistoIds.end())
	    {
	      int thisId = HistoIds.at(hname);
	      G4AnalysisManager* analysisManager = G4AnalysisManager::Instance();
	      analysisManager->FillH1(thisId, Ek/A, 1.);
	      // G4cout<<"Filling "<<hname<<G4endl;	      
	    }
	}//end check in acceptance	  
    }//end loop on angles
  
}
 
void HistoManager::Finish() 
{   
 if (fOn) 
   {
    G4AnalysisManager* manager = G4AnalysisManager::Instance();    
    manager -> Write();
    manager -> CloseFile();  

    // G4cout << "\n----> Histograms saved\n" << G4endl;      

    //delete G4AnalysisManager::Instance();
    fOn = false;
   }
}
