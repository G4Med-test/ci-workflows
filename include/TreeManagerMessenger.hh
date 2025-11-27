#ifndef TreeManagerMessenger_h
#define TreeManagerMessenger_h

#include "G4UImessenger.hh"

class TreeManagerHelper;
class G4UIdirectory;
class G4UIcmdWithAString;
class G4UIcmdWithABool;
class G4UIcmdWithAnInteger;

class TreeManagerMessenger: public G4UImessenger {

public:
  TreeManagerMessenger(TreeManagerHelper*);
  virtual ~TreeManagerMessenger();
  void SetNewValue(G4UIcommand*, G4String);

private:
  TreeManagerHelper* treeManager;
  G4UIdirectory* treeManagerDir;
  G4UIcmdWithAString* selectFileName;
  
};

#endif
