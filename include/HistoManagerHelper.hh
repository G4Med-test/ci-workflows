#ifndef HISTO_MANAGER_HELPER_HH
#define HISTO_MANAGER_HELPER_HH

#include "globals.hh"

class HistoManagerMessenger;

class HistoManagerHelper {

public:
  static HistoManagerHelper* Instance();

  inline void SetOutputFilename(const std::string filename) {fFileName = filename;};
  inline G4String GetOutFileName(){return fFileName;};
  ~HistoManagerHelper();
  
protected:
  HistoManagerHelper();

private:
  static HistoManagerHelper* instance;
  G4String fFileName;
  HistoManagerMessenger* fMessenger;
};
#endif // HISTO_MANAGER_HELPER_HH

