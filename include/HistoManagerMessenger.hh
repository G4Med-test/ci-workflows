#ifndef HistoManagerMessenger_h
#define HistoManagerMessenger_h

#include "G4UImessenger.hh"

class HistoManagerHelper;
class G4UIdirectory;
class G4UIcmdWithAString;
class G4UIcmdWithABool;
class G4UIcmdWithAnInteger;

class HistoManagerMessenger: public G4UImessenger {

public:
  HistoManagerMessenger(HistoManagerHelper*);
  virtual ~HistoManagerMessenger();
  void SetNewValue(G4UIcommand*, G4String);

private:
  HistoManagerHelper* histoManager;
  G4UIdirectory* histoManagerDir;
  G4UIcmdWithAString* selectFileName;
  
};

#endif
