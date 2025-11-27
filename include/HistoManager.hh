#ifndef HISTO_MANAGER_HH
#define HISTO_MANAGER_HH

#include "globals.hh"
#include "G4AnalysisManager.hh"
//#include "g4csv.hh"
//#include "g4xml.hh"

class HistoManager {

 public:
   HistoManager();    

  void Book(); // booking the output file
  // void SetOutputFilename(const std::string filename) {fFileName = filename;};

   // Destructor: 
   virtual ~HistoManager();

  void FillSecondaries(const G4int A, const G4int Z,
		       const G4double Ek, const G4double theta);
  // Information about secondary particles

  void Finish();
  // Close the ROOT file with all the results stored in nutples 



private:

  const std::vector<int> As = {1, 2, 3, 4, 6, 7, 7, 9, 10, 11};
  const std::vector<int> Zs = {1, 1, 1, 2, 3, 3, 4, 4,  5,  5};
  std::map<std::string, int> HistoIds;

  G4bool fOn; 

};
#endif // HISTO_MANAGER_HH
