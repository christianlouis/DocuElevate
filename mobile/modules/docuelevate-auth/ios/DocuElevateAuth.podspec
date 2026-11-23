Pod::Spec.new do |s|
  s.name = 'DocuElevateAuth'
  s.version = '1.0.0'
  s.summary = 'DocuElevate shared Keychain authentication bridge'
  s.homepage = 'https://docuelevate.org'
  s.license = { :type => 'Apache-2.0' }
  s.author = 'DocuElevate'
  s.source = { :git => 'https://github.com/christianlouis/DocuElevate.git', :tag => s.version }
  s.platforms = { :ios => '15.0' }
  s.source_files = '**/*.{swift,h,m}'
  s.dependency 'ExpoModulesCore'
end
