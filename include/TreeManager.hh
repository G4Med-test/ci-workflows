#ifndef TREE_MANAGER_HH
#define TREE_MANAGER_HH

#include "globals.hh"
#include "G4AnalysisManager.hh"

class TreeManager {

 public:
   // The analysis class is designed to be a singleton (i.e. only one instance
   // can exist). A member function called Instance is defined, which allows 
   // the user to get a pointer to the existing instance or to create it if 
   // it does not yet exist
   // 
   static TreeManager* Instance();

   // The analysis class instance can be deleted by calling the Destroy
   // method (NOTE: The class destructor is protected, and can thus not be
   // called directly):
   static void Destroy();

  void Book(); // booking the ROOT file
  // void SetOutputFilename(const std::string filename) {fFileName = filename;};

   // Destructor: 
   virtual ~TreeManager();

  void FillSecondaries(const G4int A, const G4int Z, const G4double Ek, const G4double theta);
  // Information about secondary particles

  void Finish();
  // Close the ROOT file with all the results stored in nutples 

 protected:
   // Constructor (protected):
   TreeManager();    

private:
  // The static instance of the AnalysisManager class:
  static TreeManager* instance;

  // G4String fFileName;
  
  G4int fAid;
  G4int fZid;     
  G4int fEkid;    
  G4int fThetaid;

  G4int fTupleid;

  G4bool fOn; 

};
#endif // TREE_MANAGER_HH
