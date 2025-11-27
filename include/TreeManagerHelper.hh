#ifndef TREE_MANAGER_HELPER_HH
#define TREE_MANAGER_HELPER_HH

#include "globals.hh"

class TreeManagerMessenger;

class TreeManagerHelper {

public:
  static TreeManagerHelper* Instance();

  inline void SetOutputFilename(const std::string filename) {fFileName = filename;};
  inline G4String GetOutFileName(){return fFileName;};
  ~TreeManagerHelper();
  
protected:
  TreeManagerHelper();

private:
  static TreeManagerHelper* instance;
  G4String fFileName;
  TreeManagerMessenger* fMessenger;
};
#endif // TREE_MANAGER_HELPER_HH

